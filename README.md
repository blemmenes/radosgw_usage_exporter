# Ceph RADOSGW Usage Exporter

[Prometheus](https://prometheus.io/) exporter that scrapes
[Ceph](http://ceph.com/) Ceph Object Gateway (RGW) usage information: operations and buckets.
This information is gathered using the
[Admin Operations API](http://docs.ceph.com/docs/master/radosgw/adminops/).

This exporter was based on both
(https://www.robustperception.io/writing-a-jenkins-exporter-in-python/) and the
more elaborate Jenkins exporter found at 
(https://github.com/lovoo/jenkins_exporter).

## Requirements

* Functional Ceph Cluster with the Ceph Object Gateway.
* Ceph RGW services must be configured to gather usage information as this is not
on by default. At a miniumum this may be enabled via `ceph.conf` as below. There are
also other options that should be considered
[here](http://docs.ceph.com/docs/master/radosgw/config-ref/).
```
rgw_enable_usage_log = true
```

* Configure admin entry point (default is 'admin'):
```
rgw_admin_entry = "admin"
```

* Enable admin API (default is enabled):
```
rgw_enable_apis = "s3, admin"
```

* This exporter requires a user that has the following capabilities; see the Admin Guide
[here](http://docs.ceph.com/docs/master/radosgw/admin/#add-remove-admin-capabilities)
for more details.

```
    "caps": [
        {
            "type": "buckets",
            "perm": "read"
        },
        {
            "type": "metadata",
            "perm": "read"
        },
        {
            "type": "usage",
            "perm": "read"
        },
        {
            "type": "users",
            "perm": "read"
        }
```

**Note:** If using a load balancer in front of your RGWs, please ensure that
 your timeouts are set appropriately.  When a cluster hosts a large number of
 buckets or a large number of users+buckets, usage queries may exceed the
 load balancer's timeout. 

For `haproxy` the relevant timeout is `timeout server`.

## Local Installation
```
git clone git@github.com:blemmenes/radosgw_usage_exporter.git
cd radosgw_usage_exporter
pip install requirements.txt
```

### Usage
```
usage: radosgw_usage_exporter.py [-h] [-H HOST] [-e ADMIN_ENTRY]
                                 [-a ACCESS_KEY] [-s SECRET_KEY] [-p PORT]

The required arguments are the RGW IP address and port as well as the admin S3 access key
and secret key.

Optional arguments:
  -h, --help            Show this help message and exit
  -H HOST, --host HOST  URL for the RGW API (example:
                        http://objects.dreamhost.com/)
  -e ADMIN_ENTRY, --admin_entry ADMIN_ENTRY
                        The entry point for an admin request URL [default is
                        'admin']
  -a ACCESS_KEY, --access_key ACCESS_KEY
                        S3 access key
  -s SECRET_KEY, --secret_key SECRET_KEY
                        S3 secret key
  -p PORT, --port PORT  TCP port
```

### Example
```
./check_ceph_rgw_api -H https://objects.dreamhost.com/ -a JXUABTZZYHAFLCMF9VYV -s jjP8RDD0R156atS6ACSy2vNdJLdEPM0TJQ5jD1pw
```

## Docker Usage
Docker build (https://hub.docker.com/r/blemmenes/radosgw_usage_exporter/):
```
docker run -d -p 9242 blemmenes/radosgw_usage_exporter:latest \
-H <RADOSGW HOST> -a <ACCESS_KEY> -s <SECRET_KEY> -p 9242
```
Arguments can also be specified by environment variables as well.
```
docker run -d -p 9242:9242 \
-e "RADOSGW_SERVER=<host>" \
-e "VIRTUAL_PORT=9242" \
-e "ACCESS_KEY=<access_key>" \
-e "SECRET_KEY=<secret_key>" \
blemmenes/radosgw_usage_exporter:latest
```

Metrics may be retrieved via `wget` or `curl`, or scraped by your Prometheus
system against the `http://<exporter host>:9242/metrics` endpoint.
