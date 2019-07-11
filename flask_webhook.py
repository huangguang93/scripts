import requests
import json
import logging.handlers
from flask import Flask
from flask import request

app = Flask(__name__)


handler = logging.handlers.RotatingFileHandler(
    filename="/data/logs/webhook.log",
    maxBytes=10240 * 1024,
    backupCount=2,
    encoding='UTF-8'
)
handler.setLevel(logging.DEBUG)
handler.setFormatter(logging.Formatter('%(asctime)s pid:%(process)d %(filename)s:%(lineno)d %(levelname)s %(message)s'))
app.logger.addHandler(handler)


def send_requests(method="get", url=None, headers=None, params=None, payload=None, timeout=20):
    """发送http请求"""
    try:
        resp = requests.request(
            method=method.lower(),
            url=url,
            headers=headers,
            params=params,
            data=payload,
            timeout=timeout)
        if resp.status_code == requests.codes.ok:
            return 0, resp
        else:
            return 1, "response error status code"
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


@app.route('/api/grafana/alerts', methods=['POST', 'put'])
def grafana_alerts():
    """
    # http://docs.jinkan.org/docs/flask/api.html#id4
    # https://grafana.com/docs/alerting/notifications/
    {
        "title": "My alert",
        "ruleId": 1,
        "ruleName": "Load peaking!",
        "ruleUrl": "http://url.to.grafana/db/dashboard/my_dashboard?panelId=2",
        "state": "alerting",
        "imageUrl": "http://s3.image.url",
        "message": "Load is peaking. Make sure the traffic is real and spin up more webfronts",
        "evalMatches": [
            {
                "metric": "requests",
                "tags": {},
                "value": 122
            }
        ]
    }
    :return:
    """
    json_body = request.json
    app.logger.info(json_body)
    title = json_body["title"]
    rule_id = json_body["ruleId"]
    rule_name = json_body["ruleName"]
    rule_url = json_body["ruleUrl"]
    state = json_body["state"]
    # 可能未指定图片
    try:
        image_url = json_body["imageUrl"]
    except:
        image_url = None
    message = json_body["message"]
    matches = json_body["evalMatches"]

    content = "【Grafana告警】\n"
    content += "报警主题 = {}\n".format(title)
    content += "报警触发规则 = {}\n".format(rule_name)
    content += "状态 = {}\n".format(state)
    content += "message = {}\n".format(message)
    content += "当前数值信息\n"
    for i in matches:
        content += "    {} = {}".format(i["metric"], i["value"])

    url = "http://game-msg-center.online.qiyi.qae/send/hotchat/alter/txt-msg"
    headers = {"Content-Type": "application/json"}
    payload = {"to": "zhouhuang,hujun", "msg": content}
    send_requests(method="post", url=url, headers=headers, payload=json.dumps(payload))
    return 'ok'


@app.route('/api/prometheus/alerts', methods=['POST', 'put'])
def prometheus_alerts():
    """
    prometheus alertmamager webhook接口
    总结：重要的报警信息都在alerts字段中，将alerts中的数据拼装发送展示即可
    # https://prometheus.io/docs/alerting/configuration/#webhook_config
    {
        "version": "4",
        "groupKey": <string>,    // key identifying the group of alerts (e.g. to deduplicate)
        "status": "<resolved|firing>",
        "receiver": <string>,
        "groupLabels": <object>,
        "commonLabels": <object>,
        "commonAnnotations": <object>,
        "externalURL": <string>,  // backlink to the Alertmanager.
        "alerts": [
            {
                "status": "<resolved|firing>",
                "labels": <object>,  {k:v, k:v}
                "annotations": <object>,  {"description": "xxx", "summary": "xxx"}
                "startsAt": "<rfc3339>",
                "endsAt": "<rfc3339>",
                "generatorURL": <string> // identifies the entity that caused the alert
            },
            ...
        ]
    }
    :return:
    """
    json_body = request.json
    app.logger.info(json_body)
    alerts = json_body["alerts"]
    content = "【Prometheus告警】\n"
    for i in alerts:
        status = i["status"]   # 状态
        lables = i["labels"]  # 标签dict
        annotations = i["annotations"]  # 描述dict  key: description, summary
        starts_at = i["startsAt"]  # 开始时间
        ends_at = i["endsAt"]   # 结束时间
        generator_url = i["generatorURL"]  # 报警uri查看地址

        content += "[status]: {}\n".format(status)
        content += "[description]: {}\n".format(annotations["description"])
        content += "[summary]: {}\n".format(annotations["summary"])
        content += "[Lables]:\n"
        for k, v in lables.items():
            content += "{} = {}\n".format(k, v)
        content += "[开始时间]: {}\n".format(starts_at)
        content += "[结束时间]: {}\n".format(ends_at)
        content += "[链接]: {}\n\n".format(generator_url)

    user = request.args.get('user', "zhouhuang")
    url = "http://game-msg-center.online.qiyi.qae/send/hotchat/alter/txt-msg"
    headers = {"Content-Type": "application/json"}
    payload = {"to": user, "msg": content}
    send_requests(method="post", url=url, headers=headers, payload=json.dumps(payload))
    return 'ok'


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9999)
