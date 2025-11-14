#!/usr/bin/python
# -*- coding: utf-8 -*-

import time
import requests
import warnings
import logging
import json
import argparse
import os
import re
from awsauth import S3Auth
from prometheus_client import start_http_server
from collections import defaultdict, Counter
from prometheus_client.core import GaugeMetricFamily, CounterMetricFamily, REGISTRY


class RADOSGWCollector(object):
    """RADOSGWCollector gathers bucket level usage data for all buckets from
    the specified RADOSGW and presents it in a format suitable for pulling via
    a Prometheus server.

    NOTE: By default RADOSGW Servers do not gather usage data and it must be
    enabled by 'rgw enable usage log = true' in the appropriate section
    of ceph.conf see Ceph documentation for details"""

    def __init__(
        self, host, admin_entry, access_key, secret_key, store, insecure, timeout, tag_list, enable_namespace_extraction, obc_name_prefix
    ):
        super(RADOSGWCollector, self).__init__()
        self.host = host
        self.access_key = access_key
        self.secret_key = secret_key
        self.store = store
        self.insecure = insecure
        self.timeout = timeout
        self.tag_list = tag_list
        self.enable_namespace_extraction = enable_namespace_extraction
        self.obc_name_prefix = obc_name_prefix

        # helpers for default schema
        if not self.host.startswith("http"):
            self.host = "http://{0}".format(self.host)
        # and for request_uri
        if not self.host.endswith("/"):
            self.host = "{0}/".format(self.host)

        self.url = "{0}{1}/".format(self.host, admin_entry)
        # Prepare Requests Session
        self._session()

    def collect(self):
        """
        * Collect 'usage' data:
            http://docs.ceph.com/docs/master/radosgw/adminops/#get-usage
        * Collect 'bucket' data:
            http://docs.ceph.com/docs/master/radosgw/adminops/#get-bucket-info
        """

        start = time.time()
        # setup empty prometheus metrics
        self._setup_empty_prometheus_metrics(args="")

        # setup dict for aggregating bucket usage accross "bins"
        self.usage_dict = defaultdict(dict)

        rgw_usage = self._request_data(query="usage", args="show-summary=False")
        rgw_bucket = self._request_data(query="bucket", args="stats=True")
        rgw_users = self._get_rgw_users()

        # populate metrics with data
        if rgw_usage:
            for entry in rgw_usage["entries"]:
                self._get_usage(entry)
            self._update_usage_metrics()

        if rgw_bucket:
            for bucket in rgw_bucket:
                self._get_bucket_usage(bucket)

        if rgw_users:
            for user in rgw_users:
                self._get_user_info(user)

        duration = time.time() - start
        self._prometheus_metrics["scrape_duration_seconds"].add_metric([], duration)

        for metric in list(self._prometheus_metrics.values()):
            yield metric

    def _session(self):
        """
        Setup Requests connection settings.
        """
        self.session = requests.Session()
        self.session_adapter = requests.adapters.HTTPAdapter(
            pool_connections=10, pool_maxsize=10
        )
        self.session.mount("http://", self.session_adapter)
        self.session.mount("https://", self.session_adapter)

        # Inversion of condition, when '--insecure' is defined we disable
        # requests warning about certificate hostname mismatch.
        if not self.insecure:
            warnings.filterwarnings("ignore", message="Unverified HTTPS request")
        logging.debug("Perform insecured requests")

    def _request_data(self, query, args):
        """
        Requests data from RGW. If admin entry and caps is fine - return
        JSON data, otherwise return NoneType.
        """
        url = "{0}{1}/?format=json&{2}".format(self.url, query, args)

        try:
            response = self.session.get(
                url,
                verify=self.insecure,
                timeout=float(self.timeout),
                auth=S3Auth(self.access_key, self.secret_key, self.host),
            )

            if response.status_code == requests.codes.ok:
                logging.debug(response)
                return response.json()
            else:
                # Usage caps absent or wrong admin entry
                logging.error(
                    (
                        "Request error [{0}]: {1}".format(
                            response.status_code, response.content.decode("utf-8")
                        )
                    )
                )
                return

        # DNS, connection errors, etc
        except requests.exceptions.RequestException as e:
            logging.info(("Request error: {0}".format(e)))
            return

    def _setup_empty_prometheus_metrics(self, args):
        """
        The metrics we want to export.
        """

        b_labels = ["bucket", "owner", "category", "store"]
        if self.tag_list:
            b_labels = b_labels + self.tag_list.split(",")
        if self.enable_namespace_extraction:
            b_labels.append("namespace")

        self._prometheus_metrics = {
            "ops": CounterMetricFamily(
                "radosgw_usage_ops_total",
                "Number of operations",
                labels=b_labels,
            ),
            "successful_ops": CounterMetricFamily(
                "radosgw_usage_successful_ops_total",
                "Number of successful operations",
                labels=b_labels,
            ),
            "bytes_sent": CounterMetricFamily(
                "radosgw_usage_sent_bytes_total",
                "Bytes sent by the RADOSGW",
                labels=b_labels,
            ),
            "bytes_received": CounterMetricFamily(
                "radosgw_usage_received_bytes_total",
                "Bytes received by the RADOSGW",
                labels=b_labels,
            ),
            "bucket_usage_bytes": GaugeMetricFamily(
                "radosgw_usage_bucket_bytes",
                "Bucket used bytes",
                labels=b_labels,
            ),
            "bucket_utilized_bytes": GaugeMetricFamily(
                "radosgw_usage_bucket_utilized_bytes",
                "Bucket utilized bytes",
                labels=b_labels,
            ),
            "bucket_usage_objects": GaugeMetricFamily(
                "radosgw_usage_bucket_objects",
                "Number of objects in bucket",
                labels=b_labels,
            ),
            "bucket_quota_enabled": GaugeMetricFamily(
                "radosgw_usage_bucket_quota_enabled",
                "Quota enabled for bucket",
                labels=b_labels,
            ),
            "bucket_quota_max_size": GaugeMetricFamily(
                "radosgw_usage_bucket_quota_size",
                "Maximum allowed bucket size",
                labels=b_labels,
            ),
            "bucket_quota_max_size_bytes": GaugeMetricFamily(
                "radosgw_usage_bucket_quota_size_bytes",
                "Maximum allowed bucket size in bytes",
                labels=b_labels,
            ),
            "bucket_quota_max_objects": GaugeMetricFamily(
                "radosgw_usage_bucket_quota_size_objects",
                "Maximum allowed bucket size in number of objects",
                labels=b_labels,
            ),
            "bucket_shards": GaugeMetricFamily(
                "radosgw_usage_bucket_shards",
                "Number ob shards in bucket",
                labels=b_labels,
            ),
            "user_metadata": GaugeMetricFamily(
                "radosgw_user_metadata",
                "User metadata",
                labels=["user", "display_name", "email", "storage_class", "store"],
            ),
            "user_quota_enabled": GaugeMetricFamily(
                "radosgw_usage_user_quota_enabled",
                "User quota enabled",
                labels=["user", "store"],
            ),
            "user_quota_max_size": GaugeMetricFamily(
                "radosgw_usage_user_quota_size",
                "Maximum allowed size for user",
                labels=["user", "store"],
            ),
            "user_quota_max_size_bytes": GaugeMetricFamily(
                "radosgw_usage_user_quota_size_bytes",
                "Maximum allowed size in bytes for user",
                labels=["user", "store"],
            ),
            "user_quota_max_objects": GaugeMetricFamily(
                "radosgw_usage_user_quota_size_objects",
                "Maximum allowed number of objects across all user buckets",
                labels=["user", "store"],
            ),
            "user_bucket_quota_enabled": GaugeMetricFamily(
                "radosgw_usage_user_bucket_quota_enabled",
                "User per-bucket-quota enabled",
                labels=["user", "store"],
            ),
            "user_bucket_quota_max_size": GaugeMetricFamily(
                "radosgw_usage_user_bucket_quota_size",
                "Maximum allowed size for each bucket of user",
                labels=["user", "store"],
            ),
            "user_bucket_quota_max_size_bytes": GaugeMetricFamily(
                "radosgw_usage_user_bucket_quota_size_bytes",
                "Maximum allowed size bytes size for each bucket of user",
                labels=["user", "store"],
            ),
            "user_bucket_quota_max_objects": GaugeMetricFamily(
                "radosgw_usage_user_bucket_quota_size_objects",
                "Maximum allowed number of objects in each user bucket",
                labels=["user", "store"],
            ),
            "user_total_objects": GaugeMetricFamily(
                "radosgw_usage_user_total_objects",
                "Usage of objects by user",
                labels=["user", "store"],
            ),
            "user_total_bytes": GaugeMetricFamily(
                "radosgw_usage_user_total_bytes",
                "Usage of bytes by user",
                labels=["user", "store"],
            ),
            "scrape_duration_seconds": GaugeMetricFamily(
                "radosgw_usage_scrape_duration_seconds",
                "Ammount of time each scrape takes",
                labels=[],
            ),
        }

    def _get_usage(self, entry):
        """
        Recieves JSON object 'entity' that contains all the buckets relating
        to a given RGW UID. Builds a dictionary of metric data in order to
        handle UIDs where the usage data is truncated into multiple 1000
        entry bins.
        """

        if "owner" in entry:
            bucket_owner = entry["owner"]
        # Luminous
        elif "user" in entry:
            bucket_owner = entry["user"]

        if bucket_owner not in list(self.usage_dict.keys()):
            self.usage_dict[bucket_owner] = defaultdict(dict)

        for bucket in entry["buckets"]:
            logging.debug((json.dumps(bucket, indent=4, sort_keys=True)))

            if not bucket["bucket"]:
                bucket_name = "bucket_root"
            else:
                bucket_name = bucket["bucket"]

            if bucket_name not in list(self.usage_dict[bucket_owner].keys()):
                self.usage_dict[bucket_owner][bucket_name] = defaultdict(dict)

            for category in bucket["categories"]:
                category_name = category["category"]
                if category_name not in list(
                    self.usage_dict[bucket_owner][bucket_name].keys()
                ):
                    self.usage_dict[bucket_owner][bucket_name][
                        category_name
                    ] = Counter()
                c = self.usage_dict[bucket_owner][bucket_name][category_name]
                c.update(
                    {
                        "ops": category["ops"],
                        "successful_ops": category["successful_ops"],
                        "bytes_sent": category["bytes_sent"],
                        "bytes_received": category["bytes_received"],
                    }
                )

    def _update_usage_metrics(self):
        """
        Update promethes metrics with bucket usage data
        """

        for bucket_owner in list(self.usage_dict.keys()):
            for bucket_name in list(self.usage_dict[bucket_owner].keys()):
                for category in list(self.usage_dict[bucket_owner][bucket_name].keys()):
                    data_dict = self.usage_dict[bucket_owner][bucket_name][category]

                    # Build metrics labels to match the label schema
                    u_metrics = [bucket_name, bucket_owner, category, self.store]

                    # Add empty strings for tag labels (usage API doesn't provide tags)
                    if self.tag_list:
                        u_metrics = u_metrics + [""] * len(self.tag_list.split(","))

                    # Add namespace if extraction is enabled
                    if self.enable_namespace_extraction:
                        bucket_namespace = get_bucket_namespace(bucket_name, bucket_owner, self.obc_name_prefix)
                        u_metrics.append(bucket_namespace)

                    self._prometheus_metrics["ops"].add_metric(
                        u_metrics,
                        data_dict["ops"],
                    )

                    self._prometheus_metrics["successful_ops"].add_metric(
                        u_metrics,
                        data_dict["successful_ops"],
                    )

                    self._prometheus_metrics["bytes_sent"].add_metric(
                        u_metrics,
                        data_dict["bytes_sent"],
                    )

                    self._prometheus_metrics["bytes_received"].add_metric(
                        u_metrics,
                        data_dict["bytes_received"],
                    )

    def _get_bucket_usage(self, bucket):
        """
        Method get actual bucket usage (in bytes).
        Some skips and adjustments for various Ceph releases.
        """
        logging.debug((json.dumps(bucket, indent=4, sort_keys=True)))

        if type(bucket) is dict:
            bucket_name = bucket["bucket"]
            bucket_owner = bucket["owner"]
            bucket_shards = bucket["num_shards"]
            bucket_usage_bytes = 0
            bucket_utilized_bytes = 0
            bucket_usage_objects = 0
            if self.enable_namespace_extraction:
                bucket_namespace = get_bucket_namespace(bucket_name, bucket_owner, self.obc_name_prefix)

            if bucket["usage"] and "rgw.main" in bucket["usage"]:
                # Prefer bytes, instead kbytes
                if "size_actual" in bucket["usage"]["rgw.main"]:
                    bucket_usage_bytes = bucket["usage"]["rgw.main"]["size_actual"]
                # Hammer don't have bytes field
                elif "size_kb_actual" in bucket["usage"]["rgw.main"]:
                    usage_kb = bucket["usage"]["rgw.main"]["size_kb_actual"]
                    bucket_usage_bytes = usage_kb * 1024

                # Compressed buckets, since Kraken
                if "size_utilized" in bucket["usage"]["rgw.main"]:
                    bucket_utilized_bytes = bucket["usage"]["rgw.main"]["size_utilized"]

                # Get number of objects in bucket
                if "num_objects" in bucket["usage"]["rgw.main"]:
                    bucket_usage_objects = bucket["usage"]["rgw.main"]["num_objects"]

            if "zonegroup" in bucket:
                bucket_zonegroup = bucket["zonegroup"]
            # Hammer
            else:
                bucket_zonegroup = "0"


            taglist = []
            if self.tag_list:
                bucket_tagset = bucket.get("tagset", {})
                for k in self.tag_list.split(","):
                    taglist.append(bucket_tagset.get(k, ""))

            b_metrics = [bucket_name, bucket_owner, bucket_zonegroup, self.store]
            if taglist:
                b_metrics = b_metrics + taglist
            if self.enable_namespace_extraction:
                b_metrics.append(bucket_namespace)

            self._prometheus_metrics["bucket_usage_bytes"].add_metric(
                b_metrics,
                bucket_usage_bytes,
            )

            self._prometheus_metrics["bucket_utilized_bytes"].add_metric(
                b_metrics,
                bucket_utilized_bytes,
            )

            self._prometheus_metrics["bucket_usage_objects"].add_metric(
                b_metrics,
                bucket_usage_objects,
            )

            if "bucket_quota" in bucket:
                self._prometheus_metrics["bucket_quota_enabled"].add_metric(
                    b_metrics,
                    bucket["bucket_quota"]["enabled"],
                )
                self._prometheus_metrics["bucket_quota_max_size"].add_metric(
                    b_metrics,
                    bucket["bucket_quota"]["max_size"],
                )
                self._prometheus_metrics["bucket_quota_max_size_bytes"].add_metric(
                    b_metrics,
                    bucket["bucket_quota"]["max_size_kb"] * 1024,
                )
                self._prometheus_metrics["bucket_quota_max_objects"].add_metric(
                    b_metrics,
                    bucket["bucket_quota"]["max_objects"],
                )

            self._prometheus_metrics["bucket_shards"].add_metric(
                b_metrics,
                bucket_shards,
            )

        else:
            # Hammer junk, just skip it
            pass

    def _get_rgw_users(self):
        """
        API request to get users.
        """

        rgw_users = self._request_data(query="user", args="list")

        if rgw_users and "keys" in rgw_users:
            return rgw_users["keys"]
        else:
            # Compat with old Ceph versions (pre 12.2.13/13.2.9)
            rgw_metadata_users = self._request_data(query="metadata/user", args="")
            return rgw_metadata_users

        return

    def _get_user_info(self, user):
        """
        Method to get the info on a specific user(s).
        """
        user_info = self._request_data(
            query="user", args="uid={0}&stats=True".format(user)
        )
        logging.debug((json.dumps(user_info, indent=4, sort_keys=True)))

        if "display_name" in user_info:
            user_display_name = user_info["display_name"]
        else:
            user_display_name = ""
        if "email" in user_info:
            user_email = user_info["email"]
        else:
            user_email = ""
        # Nautilus+
        if "default_storage_class" in user_info:
            user_storage_class = user_info["default_storage_class"]
        else:
            user_storage_class = ""

        self._prometheus_metrics["user_metadata"].add_metric(
            [user, user_display_name, user_email, user_storage_class, self.store], 1
        )

        if "stats" in user_info:
            self._prometheus_metrics["user_total_bytes"].add_metric(
                [user, self.store], user_info["stats"]["size_actual"]
            )
            self._prometheus_metrics["user_total_objects"].add_metric(
                [user, self.store], user_info["stats"]["num_objects"]
            )

        if "user_quota" in user_info:
            quota = user_info["user_quota"]
            self._prometheus_metrics["user_quota_enabled"].add_metric(
                [user, self.store], quota["enabled"]
            )
            self._prometheus_metrics["user_quota_max_size"].add_metric(
                [user, self.store], quota["max_size"]
            )
            self._prometheus_metrics["user_quota_max_size_bytes"].add_metric(
                [user, self.store], quota["max_size_kb"] * 1024
            )
            self._prometheus_metrics["user_quota_max_objects"].add_metric(
                [user, self.store], quota["max_objects"]
            )

        if "bucket_quota" in user_info:
            quota = user_info["bucket_quota"]
            self._prometheus_metrics["user_bucket_quota_enabled"].add_metric(
                [user, self.store], quota["enabled"]
            )
            self._prometheus_metrics["user_bucket_quota_max_size"].add_metric(
                [user, self.store], quota["max_size"]
            )
            self._prometheus_metrics["user_bucket_quota_max_size_bytes"].add_metric(
                [user, self.store], quota["max_size_kb"] * 1024
            )
            self._prometheus_metrics["user_bucket_quota_max_objects"].add_metric(
                [user, self.store], quota["max_objects"]
            )


def parse_args():
    parser = argparse.ArgumentParser(
        description="RADOSGW address and local binding port as well as \
        S3 access_key and secret_key"
    )
    parser.add_argument(
        "-H",
        "--host",
        required=False,
        help="Server URL for the RADOSGW api (example: http://objects.dreamhost.com/)",
        default=os.environ.get("RADOSGW_SERVER", "http://radosgw:80"),
    )
    parser.add_argument(
        "-e",
        "--admin-entry",
        required=False,
        help="The entry point for an admin request URL [default is '%(default)s']",
        default=os.environ.get("ADMIN_ENTRY", "admin"),
    )
    parser.add_argument(
        "-a",
        "--access-key",
        required=False,
        help="S3 access key",
        default=os.environ.get("ACCESS_KEY", "NA"),
    )
    parser.add_argument(
        "-s",
        "--secret-key",
        required=False,
        help="S3 secret key",
        default=os.environ.get("SECRET_KEY", "NA"),
    )
    parser.add_argument(
        "-k",
        "--insecure",
        help="Allow insecure server connections when using SSL",
        action="store_false",
    )
    parser.add_argument(
        "-p",
        "--port",
        required=False,
        type=int,
        help="Port to listen",
        default=int(os.environ.get("VIRTUAL_PORT", "9242")),
    )
    parser.add_argument(
        "-S",
        "--store",
        required=False,
        help="Store name added to metrics",
        default=os.environ.get("STORE", "us-east-1"),
    )
    parser.add_argument(
        "-t",
        "--timeout",
        required=False,
        help="Timeout when getting metrics",
        default=os.environ.get("TIMEOUT", "60"),
    )
    parser.add_argument(
        "-l",
        "--log-level",
        required=False,
        help="Provide logging level: DEBUG, INFO, WARNING, ERROR or CRITICAL",
        default=os.environ.get("LOG_LEVEL", "INFO"),
    )
    parser.add_argument(
        "-T",
        "--tag-list",
        required=False,
        help="Add bucket tags as label (example: 'tag1,tag2,tag3') ",
        default=os.environ.get("TAG_LIST", ""),
    )
    parser.add_argument(
        "-N",
        "--enable-namespace-extraction",
        required=False,
        help="Enable extraction of namespace from bucket owner and bucket name based on Rook user name generation.",
        default=os.environ.get("ENABLE_NAMESPACE_EXTRACTION", "false").lower() == "true",
    )
    parser.add_argument(
        "--obc-name-prefix",
        required=False,
        help="Prefix that may appear before obc.Name inside the bucket name when extracting namespace",
        default=os.environ.get("OBC_NAME_PREFIX", ""),
    )
    return parser.parse_args()

def get_bucket_namespace(bucket_name, bucket_owner, obc_name_prefix):
    """
    Extract a Kubernetes namespace from a Rook-generated RGW user/bucket name.

    Rook generates user names like:
        obc-<namespace>-<obcName>-<uuid>

    However, some deployments prepend a prefix to <obcName>, so:
        obc-<namespace>-<prefix><obcName>-<uuid>

    Parameters:
        bucket_name (str): The bucket name, which typically equals <obcName>.
        bucket_owner (str): The RGW user name, typically "obc-<ns>-<name>-<uuid>".
        obc_name_prefix (str): Optional prefix added before obcName.

    Returns:
        str: The extracted namespace, or empty string if it cannot be determined.
    """

    def _strip_uuid_suffix(value):
        """
        Remove trailing '-<uuid>' from strings where <uuid> is a standard 36-char UUID.
        """
        if not value:
            return value

        uuid_len = 36
        if len(value) <= uuid_len:
            return value

        possible_uuid = value[-uuid_len:]
        if re.match(r"^[0-9a-f-]{36}$", possible_uuid, re.IGNORECASE):
            # If there's a dash just before the UUID, remove it too
            cut_index = -uuid_len - 1 if value[-uuid_len - 1] == "-" else -uuid_len
            return value[:cut_index]

        return value

    # Ensure this is a Rook OBC-style user
    if not bucket_owner.startswith("obc-"):
        return ""

    # Remove the "obc-" prefix
    owner_no_prefix = _strip_uuid_suffix(bucket_owner[len("obc-"):])
    cleaned_bucket_name = _strip_uuid_suffix(bucket_name)

    # Construct possible suffix patterns
    # Example:
    #   "-mycustomprefixbucketname"
    #   "-bucketname"
    prefixed_bucket_suffix = f"-{obc_name_prefix}{cleaned_bucket_name}"
    bucket_suffix = f"-{cleaned_bucket_name}"

    # Case 1: Owner ends with prefix+bucket
    if owner_no_prefix.endswith(prefixed_bucket_suffix):
        return owner_no_prefix[: -len(prefixed_bucket_suffix)]

    # Case 2: Owner ends with bucket (no prefix)
    if owner_no_prefix.endswith(bucket_suffix):
        return owner_no_prefix[: -len(bucket_suffix)]

    # Case 3: Bucket occurs somewhere in the owner name
    # Look for prefixed version first
    idx = owner_no_prefix.find(prefixed_bucket_suffix)
    if idx != -1:
        return owner_no_prefix[:idx]

    # Fallback: plain bucket name
    idx = owner_no_prefix.find(bucket_suffix)
    if idx != -1:
        return owner_no_prefix[:idx]

    # Case 4: Fuzzy matching - look for bucket name components
    # Split bucket name by hyphens and try to find where these parts appear in owner
    bucket_parts = cleaned_bucket_name.split("-")

    # Try to find a sequence of bucket parts within the owner string
    # This helps when bucket name is "cdp-staging-mongodb-backup"
    # and owner is "obc-staging-cdp-mongodb-backup-<uuid>"
    for i in range(len(bucket_parts)):
        for j in range(i + 1, len(bucket_parts) + 1):
            # Try progressively longer substrings from the bucket name
            bucket_substring = "-".join(bucket_parts[i:j])
            search_pattern = f"-{bucket_substring}"

            idx = owner_no_prefix.find(search_pattern)
            if idx != -1:
                # Found a match - return everything before this match
                namespace = owner_no_prefix[:idx]
                # Make sure we have a valid namespace (at least one hyphen, meaning multiple parts)
                if namespace and "-" in namespace:
                    return namespace

    return ""

def main():
    try:
        args = parse_args()
        logging.basicConfig(level=args.log_level.upper())
        REGISTRY.register(
            RADOSGWCollector(
                args.host,
                args.admin_entry,
                args.access_key,
                args.secret_key,
                args.store,
                args.insecure,
                args.timeout,
                args.tag_list,
                args.enable_namespace_extraction,
                args.obc_name_prefix,
            )
        )
        start_http_server(args.port, addr="::")
        logging.info(("Polling {0}. Serving at port: {1}".format(args.host, args.port)))
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("\nInterrupted")
        exit(0)


if __name__ == "__main__":
    main()
