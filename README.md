# Ceph RADOSGW Usage Exporter

[Prometheus](https://prometheus.io/) exporter that scrapes [Ceph](http://ceph.com/) RADOSGW usage information. This information is gathered from a RADOSGW using the [Admin Operations API](http://docs.ceph.com/docs/master/radosgw/adminops/).

This exporter was based off from both (https://www.robustperception.io/writing-a-jenkins-exporter-in-python/) and the more elaborate Jenkins exporter here (https://github.com/lovoo/jenkins_exporter)

## Requirements

* Working Ceph Cluster with Object Gateways setup.
* Ceph RADOSGWs must beconfigured to gather usage information as this is not on by default. The miniumum is to enable it via ceph.conf as below. There are however other options that are available and should be considered [here](http://docs.ceph.com/docs/master/radosgw/config-ref/)
```
rgw enable usage log = true
```

* This exporter requires a user that has a capability of ```usage=read``` see the Admin Guide [here](http://docs.ceph.com/docs/master/radosgw/admin/#add-remove-admin-capabilities) for more details. 

## Local Installation
```
git clone git@github.com:blemmenes/radosgw_usage_exporter.git
cd radosgw_usage_exporter
pip install requirements.txt
```
### Usage
```
./radosgw_usage_exporter.py -r <RADOSGW HOST> -a <ACCESS_KEY> -s <SECRET_KEY> -p 9242
```
## Docker Usage
Docker build: (https://hub.docker.com/r/blemmenes/radosgw_usage_exporter/)
```
docker run -d -p 9242 blemmenes/radosgw_usage_exporter:latest -r <RADOSGW HOST> -a <ACCESS_KEY> -s <SECRET_KEY> -p 9242
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

Resulting metrics can be then retrieved via your Prometheus server via the ```http://<exporter host>:9242/metrics``` endpoint.
