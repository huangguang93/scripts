#!/usr/bin/env python
# -*- coding: utf-8 -*-

import requests
import json
import uuid


class PyConsul(object):
    def __init__(self, host, port, token):
        self.host = host
        self.port = port
        self.token = token
        self.headers = {
            "content-type": "application/json",
            "X-Consul-Token": self.token
        }

    def http_requests(self, method="get", url=None, headers=None, params=None, data=None, timeout=2):
        try:
            resp = requests.request(
                method=method.lower(),
                url=url,
                headers=headers,
                params=params,
                data=data,
                timeout=timeout)
            if resp.status_code == requests.codes.ok:
                return 0, resp.json()
            else:
                return 1, "http code is {}, content: {}".format(resp.status_code, resp.text)
        except requests.URLRequired:
            return 1, "Missing Url"
        except requests.ConnectTimeout:
            return 1, "Connect to server timed out'"
        except requests.ConnectionError:
            return 1, "Unable connect to server"
        except requests.ReadTimeout:
            return 1, "Server timeout did not respond"
        except requests.exceptions.Timeout:
            return 1, "Server Response timeout"
        except requests.HTTPError:
            return 1, "Server Error"
        except Exception as error:
            return 1, str(error)

    def register_service(self, dc, service, node, address, port, tags=[]):
        """
        add service
        """
        id = str(uuid.uuid4())
        payload = {
            "Datacenter": dc,
            "Node": node,
            "Address": address,
            "TaggedAddresses": {
                "lan": address,
                "wan": address
            },
            "NodeMeta": {
                "somekey": "somevalue"
            },
            "Service": {
                "ID": service,
                "Service": service,
                "Tags": tags,
                "Address": address,
                "Meta": {
                    "somekey": "somevalue"
                },
                "Port": int(port)
            },
            "Check": {
                "Node": node,
                "ServiceID": service,
                "CheckID": "service:{}".format(service),
                "Name": "health check",
                "Notes": "health check",
                "Status": "passing",
                "Definition": {
                    "TCP": "{}:{}".format(address, port),
                    "Interval": "5s",
                    "Timeout": "1s",
                    "DeregisterCriticalServiceAfter": "30s"
                }
            },
            "SkipNodeUpdate": False
        }
        url = "http://{}:{}/v1/catalog/register".format(self.host, self.port)
        status, result = self.http_requests(method="put", url=url,
                                            data=json.dumps(payload),
                                            headers=self.headers)
        print(status, result)

    def list_datacenters(self):
        """
        list all datacenter
        """
        url = "http://{}:{}/v1/catalog/datacenters".format(self.host, self.port)
        status, result = self.http_requests(method="get", url=url,
                                            headers=self.headers)
        return result if status == 0 else []

    def list_services(self):
        """
        list all services
        """
        url = "http://{}:{}/v1/catalog/services".format(self.host, self.port)
        status, result = self.http_requests(method="get", url=url,
                                            headers=self.headers)
        if status == 0:
           return result.keys()

    def list_nodes_for_service(self, service_id):
        """
        This endpoint returns the nodes providing a service in a given datacenter
        """
        url = "http://{}:{}/v1/catalog/service/{}".format(self.host, self.port, service_id)
        status, result = self.http_requests(method="get", url=url,
                                            headers=self.headers)
        return result if status == 0 else []

    def remove_node(self, dc, node, service_id=None):
        """
        service_id is None delete one node, else  delete node in service_id
        """
        if service_id is None:
            payload = {
                "Datacenter": dc,
                "Node": node
            }
        else:
            payload = {
                "Datacenter": dc,
                "ServiceID": service_id,
                "Node": node
            }
        url = "http://{}:{}/v1/catalog/deregister".format(self.host, self.port)
        status, result = self.http_requests(method="put", url=url,
                                            data=json.dumps(payload),
                                            headers=self.headers)
        print(status, result)

    def remove_service(self, service_id):
        """
        delete service, all node in this service will be delete
        """
        for i in c.list_nodes_for_service(service_id):
            dc = i["Datacenter"]
            service_id = i["ServiceID"]
            node = i["Node"]
            self.remove_node(dc, node, service_id)


# test
if __name__ == '__main__':
    c = PyConsul(host="10.110.90.230", port=8500, token="")

    tags = ["idc=wuhan4_ct", "source=Lingxu", "project=test_4-php", "env=test_4"]
    dc = "prometheus_dc"
    service = "nginx_exporter"
    node = "game-operation-group-web-dev012-whdx"
    address = "10.127.23.30"
    port = "9913"
    c.register_service(dc, service, node, address, port, tags)