#!/usr/bin/python

import time
import requests
import logging
import json
import argparse
import os
from awsauth import S3Auth
from prometheus_client import start_http_server
from prometheus_client.core import GaugeMetricFamily, CounterMetricFamily, REGISTRY

logging.basicConfig(level=logging.DEBUG)
DEBUG = int(os.environ.get('DEBUG', '0'))


class RADOSGWCollector(object):
    """RADOSGWCollector gathers bucket level usage data for all buckets from
    the specified RADOSGW and presents it in a format suitable for pulling via
    a Prometheus server.

    NOTE: By default RADOSGW Servers do not gather usage data by default and
    must be enabled by 'rgw enable usage log = true' in the appropriate section
    of ceph.conf see Ceph documentation for details """

    def __init__(self, target, access_key, secret_key):
        super(RADOSGWCollector, self).__init__()
        self.target=target
        self.access_key=access_key
        self.secret_key=secret_key

    def collect(self):
        results=self._request_data()

        # setup empty prometheus metrics
        self._setup_empty_prometheus_metrics()

        # populate metrics with data
        for entry in results['entries']:
            self._process_data(entry)

        for metric in self._prometheus_metrics.values():
            yield metric

    def _request_data(self):
        # Request all bucket usage data from RADOSGW endpoint
        url='http://%s/admin/usage?format=json&show-summary=False' % self.target
        response=requests.get(url, auth=S3Auth(
                                                self.access_key,
                                                self.secret_key,
                                                self.target
                                                ))
        if response.status_code != requests.codes.ok:
            return[]
        results=response.json()

        if DEBUG:
            pprint(results)

        return results

    def _setup_empty_prometheus_metrics(self):
        # The metrics we want to export.
        self._prometheus_metrics={
            'ops':
                CounterMetricFamily('radosgw_usage_ops_total',
                                    'RADOSGW Usage number of opperations',
                                    labels=["bucket", "owner", "category"]),
            'successful_ops':
                CounterMetricFamily('radosgw_usage_successful_ops_total',
                                    'RADOSGW Usage number of successful opperations',
                                    labels=["bucket", "owner", "category"]),
            'bytes_sent':
                CounterMetricFamily('radosgw_usage_sent_bytes',
                                    'RADOSGW Usage number of bytes sent by the RADOSGW',
                                    labels=["bucket", "owner", "category"]),
            'bytes_received':
                CounterMetricFamily('radosgw_usage_received_bytes',
                                    'RADOSGW Usage number of bytes received by the RADOSGW',
                                    labels=["bucket", "owner", "category"]),
        }

    def _process_data(self, entry):
        # Recieves JSON object 'entity' that contains all the buckets relating
        # to a given RGW UID.
        bucket_owner=entry['owner']
        for bucket in entry['buckets']:
            print bucket
            if not bucket['bucket']:
                bucket_name="root"
            else:
                bucket_name=bucket['bucket']

            for category in bucket['categories']:
                self._add_data_to_prometheus(bucket_name, bucket_owner, category)

    def _add_data_to_prometheus(self, bucket_name, bucket_owner, category):
        self._prometheus_metrics['ops'].add_metric([bucket_name,
                                                    bucket_owner,
                                                    category['category']],
                                                    category['ops'])
        self._prometheus_metrics['successful_ops'].add_metric([bucket_name,
                                                    bucket_owner,
                                                    category['category']],
                                                    category['successful_ops'])
        self._prometheus_metrics['bytes_sent'].add_metric([bucket_name,
                                                    bucket_owner,
                                                    category['category']],
                                                    category['bytes_sent'])
        self._prometheus_metrics['bytes_received'].add_metric([bucket_name,
                                                    bucket_owner,
                                                    category['category']],
                                                    category['bytes_received'])


def parse_args():
    parser=argparse.ArgumentParser(
        description='RADOSGW address and local binding port as well as \
        S3 access_key and secret_key'
    )
    parser.add_argument(
        '-r', '--radosgw',
        metavar='radosgw',
        required=False,
        help='Server URL for the RADOSGW api',
        default=os.environ.get('RADOSGW_SERVER', 'http://radosgw:80')
    )
    parser.add_argument(
        '-p', '--port',
        metavar='port',
        required=False,
        type=int,
        help='Listen locally to this port',
        default=int(os.environ.get('VIRTUAL_PORT', '9255'))
    )
    parser.add_argument(
        '-a', '--access_key',
        metavar='access_key',
        required=False,
        help='S3 access key',
        default=os.environ.get('ACCESS_KEY', 'NA')
    )
    parser.add_argument(
        '-s', '--secret_key',
        metavar='secret_key',
        required=False,
        help='S3 secrest key',
        default=os.environ.get('SECRET_KEY', 'NA')
    )
    return parser.parse_args()


def main():
    try:
        args=parse_args()
        port=int(args.port)
        server=args.radosgw
        access_key=args.access_key
        secret_key=args.secret_key
        REGISTRY.register(RADOSGWCollector(server, access_key, secret_key))
        start_http_server(port)
        print "Polling %s. Serving at port: %s" % (server, port)
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print(" Interrupted")
        exit(0)


if __name__ == "__main__":
    main()
