import json
import os
import base64
import uuid
import hmac
from hashlib import sha256

import yaml
import rsa
from requests import Session


LOGINBYPASSWORD = "https://passport-api.mihoyo.com/account/ma-cn-passport/web/loginByPassword"
WEBVERIFYFORGAME = "https://passport-api.mihoyo.com/account/ma-cn-session/web/webVerifyForGame"
WEBLOGIN = "https://hk4e-sdk.mihoyo.com/hk4e_cn/combo/granter/login/webLogin"
LOGIN = "https://api-cloudgame.mihoyo.com/hk4e_cg_cn/gamer/api/login"

WALLET = 'https://api-cloudgame.mihoyo.com/hk4e_cg_cn/wallet/wallet/get'
NOTIFICATIONS = 'https://api-cloudgame.mihoyo.com/hk4e_cg_cn/gamer/api/listNotifications?status=NotificationStatusUnread&type=NotificationTypePopup&is_sort=true'
ACK_NOTIFICATIONS = "https://api-cloudgame.mihoyo.com/hk4e_cg_cn/gamer/api/ackNotification"

# PKCS1
KEY = """-----BEGIN RSA PUBLIC KEY-----
MIGJAoGBAMO96R08wc3cBiGb++S0lP5gmvtwjkNyw0qp2zHkNlfSAO5YW4iPN3AG
62shg82ZEnUbzJsMgXugNbZ4Smbmwxsv3Oz0TFcJ2+qufnWoQtuqPRfG0xMiloIc
VIjnQ98+lMVX1e3+GbJXCiSg5cWUASAKf5AKAaznZsWhgy3KL7ERAgMBAAE=
-----END RSA PUBLIC KEY-----""".encode()


key = rsa.PublicKey.load_pkcs1(KEY)


def dict2str(query: dict, delimiter: str = ";") -> str:
    return delimiter.join("=".join(item) for item in query.items())


def sign(data: dict, key: str) -> str:
    return hmac.new(key.encode(), dict2str(data, delimiter="&").encode(), sha256).hexdigest()


def login(account: str, password: str, headers: dict):
    ses = Session()
    ses.headers.update(headers)

    enc = lambda a: base64.b64encode(rsa.encrypt(a.encode(), key)).decode()
    ses.options(LOGINBYPASSWORD)
    resp = ses.post(LOGINBYPASSWORD, json={
        "account": enc(account),
        "password": enc(password),
    })
    if resp.json()["retcode"] != 0:
        raise RunError(f"Login failed! Response: {resp.json()}")
    
    ses.post(WEBVERIFYFORGAME)

    data = {"app_id": 4,"channel_id": 1}
    token_data = ses.post(WEBLOGIN, json=data).json().get("data")
    data = {
        "app_id": str(data.get("app_id")), 
        "channel_id": str(data.get("channel_id")), 
        "combo_token": token_data.get("combo_token"), 
        "open_id": token_data.get("open_id")
    }
    combo_token = {
        "ai": data.get("app_id"),
        "ci": data.get("channel_id"),
        "oi": data.get("open_id"),
        "ct": data.get("combo_token"),
        "si": sign(data, "d0d3a7342df2026a70f650b907800111"),
        "bi": "hk4e_cn"
    }
    ses.headers.update({"x-rpc-combo_token": dict2str(combo_token)})
    
    ses.post(LOGIN)

    return ses


def read_env(var_name: str, loader) -> dict:
    return loader(os.environ.get(var_name))


def read_file(file_name: str, loader):
    try:
        with open(file_name, encoding='utf-8') as fp:
            return loader(fp.read())
    except FileNotFoundError:
        return


class RunError(Exception):
    pass


yaml_loader = lambda yml: yaml.load(yml, Loader=yaml.FullLoader)
# conf = read_env('MHYY_CONFIG', yaml_loader)['accounts']
conf = read_file('config.yml', yaml_loader)['accounts']
if not conf:
    raise RunError('请正确配置环境变量或者config文件后再运行本脚本！')
print(f'检测到 {len(conf)} 个账号，正在进行任务……')

for config in conf:
    if config == '':
        raise RunError(f"请在Settings->Secrets->Actions填入配置后再运行！")
    account = config['account']
    password = config['password']
    client_type = config.get('type')
    deviceid = config.get('deviceid')
    devicename = config.get('devicename')
    devicemodel = config.get('devicemodel')
    headers = {
        'x-rpc-app_id': 'c76ync6mutq8',
        'x-rpc-client_type': str(client_type) if client_type is not None else '16',
        'x-rpc-device_id': deviceid if deviceid is not None else str(uuid.uuid4()),
        'x-rpc-device_name': devicename if devicename is not None else 'Unknown',
        'x-rpc-device_model': devicemodel if devicemodel is not None else 'Unknown',
    }
    ses = login(str(account), str(password), headers)
    
    wallet = ses.get(WALLET).json()
    if wallet['retcode'] == -100:  # {"data": None,"message": "登录已失效，请重新登录", "retcode": -100}
        raise RunError(f'当前登录已过期，请重新登陆！返回为：{wallet}')
    print(f"你当前拥有免费时长 {wallet['data']['free_time']['free_time']} 分钟，畅玩卡状态为 {wallet['data']['play_card']['short_msg']}，拥有米云币 {wallet['data']['coin']['coin_num']} 枚")
    
    notices = ses.get(NOTIFICATIONS).json()
    try:
        if len(notices['data']['list']) == 0:
            print(f'获取签到情况成功！今天是否已经签到过了呢？')
            exit(0)
        elif json.loads(notices['data']['list'][0]['msg']) == {"num": 15, "over_num": 0, "type": 2, "msg": "每日登录奖励", "func_type": 1}:
            print(f'获取签到情况成功！当前签到情况为{notices["data"]["list"][0]["msg"]}')
        elif json.loads(notices['data']['list'][0]['msg'])['over_num'] > 0:
            print(f'获取签到情况成功！当前免费时长已经达到上限！签到情况为{notices["data"]["list"][0]["msg"]}')
        else:
            raise RunError(f"获取签到信息失败！返回信息如下：{notices}")
    except IndexError:
        raise RunError(f"获取签到信息失败！返回信息如下：{notices}")

    print('正在尝试清除15分钟弹窗……')
    for notice in notices['data']['list']:
        ack_result = ses.post(ACK_NOTIFICATIONS, json={'id': str(notice['id'])}).json()
        try:
            if ack_result['retcode'] == 0:
                print(f'已清除id为{notice["id"]}的弹窗！')
            else:
                print(f'清除弹窗失败！返回信息为：{ack_result}')
        except KeyError:
            print(f'清除弹窗失败！返回信息为：{ack_result}')
