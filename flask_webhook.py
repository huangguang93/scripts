import requests
import json
from flask import Flask
from flask import request
from datetime import datetime

app = Flask(__name__)

Admin = "zhouhuang"


def http_requests(method="get", url=None, headers=None, params=None, payload=None, timeout=10):
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


def reliao_notify(user, content):
    url = "http://game-msg-center.online.qiyi.qae/send/hotchat/alter/txt-msg"
    headers = {"Content-Type": "application/json"}
    payload = {"to": user, "msg": content}
    code, msg = http_requests(method="post", url=url, headers=headers, payload=json.dumps(payload))
    if code == 1:
        return "not ok"
    return 'ok'


@app.route('/api/grafana/alerts', methods=['POST', 'PUT'])
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
    title = json_body["title"]
    rule_name = json_body["ruleName"]
    state = json_body["state"]
    message = json_body["message"]
    matches = json_body["evalMatches"]
    start_at = datetime.now().strftime( '%Y-%m-%d %H:%M:%S')

    content = "【Grafana告警】\n"
    content += "[告警状态]: {}\n".format(state)
    content += "[告警主题]: {}\n".format(title)
    content += "[详情描述]: {}\n".format(message)
    content += "[触发规则]: {}\n".format(rule_name)
    content += "[告警时间]: {}\n".format(start_at)
    content += "[数值详情]:\n"
    for i in matches:
        content += "{} = {}\n".format(i["metric"], i["value"])

    user = request.args.get('user', "zhouhuang")
    reliao_notify(user=user, content=content)
    return 'ok'


@app.route('/api/prometheus/alerts', methods=['POST', 'PUT'])
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
    status = json_body["status"]
    alerts = json_body["alerts"]  # 详细告警列表
    count = 0
    content = ""
    for i in alerts:
        if status != i["status"]:
            continue
        # generator_url = i["generatorURL"]  # 报警uri查看地址
        # annotations = i["annotations"]     # 描述dict  key: description, summary
        try:
            lables = i["labels"]               # 标签dict
            summary = i["annotations"]["summary"]  # 告警主题
            description = i["annotations"]["description"]  # 告警描述
            starts_at = i["startsAt"]          # 开始时间
            ends_at = i["endsAt"]              # 结束时间
            content += "[告警状态]: {}\n".format(status)
            content += "[告警主题]: {}\n".format(summary)
            content += "[告警描述]: {}\n".format(description)
            for k, v in lables.items():
                if k in ["alertname", "consul_address", "consul_dc"]:
                    continue
                content += "{} = {}\n".format(k, v)
            content += "[开始时间]: {}\n".format(starts_at)
            content += "[结束时间]: {}\n".format(ends_at)
            content += "\n"
            count += 1
        except KeyError as err:
            ## 异常处理
            reliao_notify(user=Admin,
                          content="Alertmanager webhook faild, info: {} key not find. alerts: {}".format(err, alerts))

    if count > 3 and status == "firing":
        content += "注意! 本次共产生{}条报警,请多留意!".format(count)

    if count > 0:
        title = "【告警通知】\n"
        user = request.args.get('user', "zhouhuang")
        reliao_notify(user=user, content=title + content)
    return 'ok'


@app.route('/api/prometheus/alerts', methods=['GET'])
def get_prometheus_alerts():
    return 'ok'


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9999)
