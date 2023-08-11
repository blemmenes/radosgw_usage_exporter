# Ceph RADOSGW Usage Exporter

[Prometheus](https://prometheus.io/) exporter that scrapes
[Ceph](http://ceph.com/) RADOSGW usage information (operations and buckets).
This information is gathered from a RADOSGW using the
[Admin Operations API](http://docs.ceph.com/docs/master/radosgw/adminops/).

This exporter was based off from both
(https://www.robustperception.io/writing-a-jenkins-exporter-in-python/) and the
more elaborate Jenkins exporter here
(https://github.com/lovoo/jenkins_exporter).

## Requirements

* Working Ceph Cluster with Object Gateways setup.
* Ceph RADOSGWs must beconfigured to gather usage information as this is not
on by default. The miniumum is to enable it via `ceph.conf` as below. There are
however other options that are available and should be considered
[here](http://docs.ceph.com/docs/master/radosgw/config-ref/). If you don't configure
thresholds, intervals, and shards you may end up having too large objects in the usage
namespace of the log pool. The values below are just examples. Check the documentation
which ones would be the best ones for your setup.

```
rgw enable usage log = true
rgw usage log flush threshold = 1024
rgw usage log tick interval = 30
rgw usage max shards = 32
rgw usage max user shards = 8

```

* Configure admin entry point (default is 'admin'):
```
rgw admin entry = "admin"
```

* Enable admin API (default is enabled):
```
rgw enable apis = "s3, admin"
```

* This exporter requires a user that has the following capability, see the Admin Guide
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

**Note:** If using a loadbalancer in front of your RADOSGWs, please make sure your timeouts are set appropriately as clusters with a large number of buckets, or large number of users+buckets could cause the usage query to exceed the loadbalancer timeout. 

For haproxy the timeout in question is `timeout server`

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

RADOSGW address and local binding port as well as S3 access_key and secret_key

optional arguments:
  -h, --help            show this help message and exit
  -H HOST, --host HOST  Server URL for the RADOSGW api (example:
                        http://objects.dreamhost.com/)
  -e ADMIN_ENTRY, --admin_entry ADMIN_ENTRY
                        The entry point for an admin request URL [default is
                        'admin']
  -a ACCESS_KEY, --access_key ACCESS_KEY
                        S3 access key
  -s SECRET_KEY, --secret_key SECRET_KEY
                        S3 secrest key
  -p PORT, --port PORT  Port to listen
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

Resulting metrics can be then retrieved via your Prometheus server via the
`http://<exporter host>:9242/metrics` endpoint.
