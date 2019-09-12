import os
import subprocess
import time
import argparse
from prometheus_client.core import GaugeMetricFamily, REGISTRY
from prometheus_client import make_wsgi_app
from wsgiref.simple_server import make_server


class CustomCollector(object):
    def __init__(self):
        self.ports = []
        self.old_ports = []
        self.success = 0  # 1: success , 1: fail
        self.info = "none"

    def collect(self):
        now = time.time()

        self.run_sh("ss -ntl")
        lost_port = set(self.old_ports) - set(self.ports)
        self.old_ports = self.ports

        duration = time.time() - now
        duration_seconds = GaugeMetricFamily('discovery_network_port_duration_seconds', 'duration_seconds', labels=[])
        duration_seconds.add_metric([], duration)
        yield duration_seconds

        job_success = GaugeMetricFamily('discovery_network_port_success', 'job result', labels=["info"])
        job_success.add_metric([self.info], self.success)
        yield job_success

        for port in self.ports:
            c = GaugeMetricFamily('discovery_network_tcp_listen_port', 'listen port', labels=['port'])
            c.add_metric([str(port)], 1)
            yield c

        for port in lost_port:
            c = GaugeMetricFamily('discovery_network_tcp_listen_port', 'listen port', labels=['port'])
            c.add_metric([str(port)], 0)
            yield c

    def run_sh(self, command):
        self.ports = []
        self.info = "none"
        try:
            sub = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            pid = sub.pid
            out_put = sub.communicate()[0]
            status = sub.returncode
        except Exception as error:
            out_put = str(error)
            self.info = str(error)
            status = 1

        if status == 0:
            self.success = 1
            output_lines = out_put.split("\n")
            try:
                for i in output_lines[1:]:
                    ii = i.split()
                    if len(ii) > 3:
                        listen_port = ii[3].split(":")[1]
                        self.ports.append(listen_port)
            except Exception as error:
                self.info = str(error)
                self.success = 0


def parse_args():
    parser = argparse.ArgumentParser(
        description='jenkins exporter args jenkins address and port'
    )
    parser.add_argument(
        '-p', '--port',
        metavar='port',
        required=False,
        type=int,
        help='Listen to this port',
        default=int(os.environ.get('VIRTUAL_PORT', '9118'))
    )
    return parser.parse_args()


def main():
    try:
        args = parse_args()
        port = int(args.port)
        REGISTRY.register(CustomCollector())
        app = make_wsgi_app()
        httpd = make_server('', port, app)
        httpd.serve_forever()
        print("Polling {}. Serving at port: {}".format(args.jenkins, port))
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print(" Interrupted")
        exit(0)


if __name__ == "__main__":
    main()
