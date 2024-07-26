import json
import os
import random
import time
import base64

import rsa
from requests import Session


LOGINBYPASSWORD = "https://passport-api.mihoyo.com/account/ma-cn-passport/web/loginByPassword"
WEBVERIFY = "https://passport-api.mihoyo.com/account/ma-cn-session/web/webVerifyForGame"
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


def login(account: str, password: str, headers):
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
    
    ses.post(WEBVERIFY)

    data = ses.post(WEBLOGIN, json={"app_id": 4,"channel_id": 1}).json().get("data")

    combo_token = {
        "ai": "4",
        "ci": "1",
        "oi": data.get("open_id"),
        "ct": data.get("combo_token"),
        "si": "c7f9c3342e2d17b1e5b02f9dc0831cdc826921759a23f8821e768d0ff100b32a", 
        "bi": "hk4e_cn"
    }
    combo_token = ";".join("=".join(item) for item in combo_token.items())
    ses.headers.update({"x-rpc-combo_token": combo_token})
    
    ses.post(LOGIN)

    return ses


def read_yml(variable_name):
    import yaml

    # Try to get the variable from the environment
    env = os.environ.get(variable_name)
    if env:
        return yaml.load(env, Loader=yaml.FullLoader)

    # If not found in environment, try to read from config.yml
    try:
        with open("config.yml", "r", encoding='utf-8') as fp:
            return yaml.load(fp, Loader=yaml.FullLoader)
    except FileNotFoundError:
        return None
    

def read_json(variable_name):
    # Try to get the variable from the environment
    env = os.environ.get(variable_name)
    if env:
        return json.loads(env)

    # If not found in environment, try to read from config.yml
    try:
        with open("config.json", "r", encoding='utf-8') as fp:
            return json.load(fp)
    except FileNotFoundError:
        return None
 

class RunError(Exception):
    pass


conf = read_json('MHYY_CONFIG')['accounts']
if not conf:
    raise RunError('请正确配置环境变量或者config文件后再运行本脚本！')
print(f'检测到 {len(conf)} 个账号，正在进行任务……')

for config in conf:
    if config == '':
        raise RunError(f"请在Settings->Secrets->Actions填入配置后再运行！")
    account = config['account']
    password = config['password']
    client_type = config['type']
    sysver = config['sysver']
    deviceid = config['deviceid']
    devicename = config['devicename']
    devicemodel = config['devicemodel']
    appid = config['appid']
    headers = {
        'x-rpc-app_id': 'c76ync6mutq8',
        'x-rpc-client_type': str(client_type),
        'x-rpc-sys_version': str(sysver),  # Previous version need to convert the type of this var
        'x-rpc-channel': 'cyydmihoyo',
        'x-rpc-device_id': deviceid,
        'x-rpc-device_name': devicename,
        'x-rpc-device_model': devicemodel,
        'x-rpc-vendor_id': '1', # 2023/8/31更新，不知道作用
        'x-rpc-cg_game_biz': 'hk4e_cn', # 游戏频道，国服就是这个
        'x-rpc-op_biz': 'clgm_cn',  # 2023/8/31更新，不知道作用
        'x-rpc-language': 'zh-cn',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0'
    }
    ses = login(str(account), str(password), headers)
    ses.headers.update(headers)
    wait_time = random.randint(1, 180) # Random Sleep to Avoid Ban
    print(f'开始休眠 {wait_time} s')
    time.sleep(wait_time)
    wallet = ses.get(WALLET)
    if wallet.json()['retcode'] == -100:  # {"data": None,"message": "登录已失效，请重新登录", "retcode": -100}
        print(f'当前登录已过期，请重新登陆！返回为：{wallet.text}')
    else:
        print(f"你当前拥有免费时长 {wallet.json()['data']['free_time']['free_time']} 分钟，畅玩卡状态为 {wallet.json()['data']['play_card']['short_msg']}，拥有米云币 {wallet.json()['data']['coin']['coin_num']} 枚")
        res = ses.get(NOTIFICATIONS)
        signed = False
        try:
            if len(res.json()['data']['list']) == 0:
                signed = True
                over = False
            elif json.loads(res.json()['data']['list'][0]['msg']) == {"num": 15, "over_num": 0, "type": 2, "msg": "每日登录奖励", "func_type": 1}:
                signed = False
                over = False
            elif json.loads(res.json()['data']['list'][0]['msg'])['over_num'] > 0:
                signed = False
                over = True
            else:
                raise RunError(f"签到失败！返回信息如下：{res.text}")
        except IndexError:
            raise RunError(f"签到失败！返回信息如下：{res.text}")

        if signed:
            print(f'获取签到情况成功！今天是否已经签到过了呢？')
            print(f'完整返回体为：{res.text}')
        elif not signed and over:
            print(f'获取签到情况成功！当前免费时长已经达到上限！签到情况为{res.json()["data"]["list"][0]["msg"]}')
            print(f'完整返回体为：{res.text}')
        else:
            print(f'获取签到情况成功！当前签到情况为{res.json()["data"]["list"][0]["msg"]}')
            print(f'完整返回体为：{res.text}')
        print('正在尝试清除15分钟弹窗……')
        for popout in res.json()['data']['list']:
            popid = popout['id']
            clear_result = ses.post(ACK_NOTIFICATIONS, json={'id': str(popid)})
            try:
                if clear_result.status_code == 200 and clear_result.json()['msg'] == 'OK':
                    print(f'已清除id为{popid}的弹窗！')
                else:
                    print(f'清除弹窗失败！返回信息为：{clear_result.json()}')
            except KeyError as e:
                print(f'清除弹窗失败！返回信息为：{clear_result.json()}；错误信息为：{e}')
