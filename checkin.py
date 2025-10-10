#!/usr/bin/env python3
"""
AnyRouter.top 自动签到脚本
"""

import asyncio
import json
import os
import sys
from datetime import datetime

import httpx
from dotenv import load_dotenv
from playwright.async_api import async_playwright

from notify import notify

load_dotenv()


def load_accounts():
	"""从环境变量加载账号配置"""
	accounts_json = os.getenv('ANYROUTER_ACCOUNTS')
	if not accounts_json:
		print('[ERROR] Environment variable ANYROUTER_ACCOUNTS not found')
		return None

	try:
		accounts = json.loads(accounts_json)
		if not accounts or not isinstance(accounts, list):
			print('[ERROR] Invalid account configuration format')
			return None
		return accounts
	except json.JSONDecodeError as e:
		print(f'[ERROR] Failed to parse account configuration: {e}')
		return None


async def get_waf_cookie():
	"""使用 Playwright 获取 WAF Cookie"""
	print('[INFO] Starting to get WAF Cookie...')
	try:
		async with async_playwright() as p:
			# 启动浏览器
			browser = await p.chromium.launch(headless=True)
			context = await browser.new_context(
				user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
			)
			page = await context.new_page()

			# 访问网站
			await page.goto('https://anyrouter.top/', wait_until='networkidle', timeout=60000)

			# 等待 Cookie 设置
			await asyncio.sleep(3)

			# 获取所有 Cookies
			cookies = await context.cookies()
			await browser.close()

			# 查找 WAF Cookie
			waf_cookie = None
			for cookie in cookies:
				if 'cf_' in cookie['name'].lower() or 'challenge' in cookie['name'].lower():
					waf_cookie = cookie
					break

			if waf_cookie:
				print(f"[SUCCESS] WAF Cookie obtained: {waf_cookie['name']}")
				return {waf_cookie['name']: waf_cookie['value']}
			else:
				print('[WARNING] No obvious WAF Cookie found, try to continue')
				# 返回所有 Cookie
				return {cookie['name']: cookie['value'] for cookie in cookies}

	except Exception as e:
		print(f'[ERROR] Failed to get WAF Cookie: {e}')
		return None


def build_headers(cookie, api_user):
	"""构建请求头"""
	# 合并 Cookie 字符串
	cookie_str = f'session={cookie}'

	return {
		'accept': 'application/json, text/plain, */*',
		'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
		'cookie': cookie_str,
		'origin': 'https://anyrouter.top',
		'referer': 'https://anyrouter.top/',
		'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
		'x-api-user': str(api_user),
	}


def check_in(client, headers):
	"""执行签到"""
	try:
		response = client.post('https://anyrouter.top/api/user/checkin', headers=headers, timeout=30)

		if response.status_code == 200:
			data = response.json()
			if data.get('success'):
				print('[SUCCESS] Check-in successful')
				return True, '[SUCCESS] Check-in successful'
			else:
				msg = data.get('message', 'Unknown error')
				if 'already' in msg.lower() or '已' in msg:
					print('[INFO] Already checked in today')
					return True, '[INFO] Already checked in today'
				else:
					print(f'[FAIL] Check-in failed: {msg}')
					return False, f'[FAIL] Check-in failed: {msg}'
		else:
			print(f'[FAIL] Request failed, status code: {response.status_code}')
			return False, f'[FAIL] Request failed, status code: {response.status_code}'
	except Exception as e:
		print(f'[FAIL] Check-in exception: {e}')
		return False, f'[FAIL] Check-in exception: {str(e)[:50]}...'


def get_user_info(client, headers):
	"""获取用户信息，返回格式化字符串和余额数值"""
	try:
		response = client.get('https://anyrouter.top/api/user/self', headers=headers, timeout=30)

		if response.status_code == 200:
			data = response.json()
			if data.get('success'):
				user_data = data.get('data', {})
				quota = round(user_data.get('quota', 0) / 500000, 2)
				used_quota = round(user_data.get('used_quota', 0) / 500000, 2)
				info_str = f':money: Current balance: ${quota}, Used: ${used_quota}'
				return info_str, quota  # 返回字符串和余额数值
	except Exception as e:
		return f'[FAIL] Failed to get user info: {str(e)[:50]}...', 0
	return None, 0


async def check_in_account(account, index):
	"""为单个账号执行签到"""
	print(f'\n[START] Processing Account {index + 1}')

	cookie = account.get('cookie')
	api_user = account.get('api_user')

	if not cookie or not api_user:
		print(f'[ERROR] Account {index + 1} configuration incomplete')
		return False, None, 0

	# 获取 WAF Cookie
	waf_cookies = await get_waf_cookie()

	# 构建请求头
	headers = build_headers(cookie, api_user)

	# 如果有 WAF Cookie，添加到请求头
	if waf_cookies:
		cookie_str = headers['cookie']
		for name, value in waf_cookies.items():
			cookie_str += f'; {name}={value}'
		headers['cookie'] = cookie_str

	# 创建 HTTP 客户端
	with httpx.Client(follow_redirects=True) as client:
		# 执行签到
		success, message = check_in(client, headers)

		# 获取用户信息
		user_info, balance = get_user_info(client, headers)

		# 输出结果
		if success:
			print(f'[SUCCESS] Account {index + 1}')
		else:
			print(f'[FAIL] Account {index + 1}')

		if user_info:
			print(user_info)

		return success, user_info, balance


async def main():
	"""主函数"""
	print('[SYSTEM] AnyRouter.top multi-account auto check-in script started (using Playwright)')
	print(f'[TIME] Execution time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')

	# 加载账号配置
	accounts = load_accounts()
	if not accounts:
		print('[FAILED] Unable to load account configuration, program exits')
		sys.exit(1)

	print(f'[INFO] Found {len(accounts)} account configurations')

	# 为每个账号执行签到
	success_count = 0
	total_count = len(accounts)
	total_balance = 0  # 累计总余额
	notification_content = []

	for i, account in enumerate(accounts):
		try:
			success, user_info, balance = await check_in_account(account, i)
			if success:
				success_count += 1
			# 累加余额
			total_balance += balance
			# 收集通知内容
			status = '[SUCCESS]' if success else '[FAIL]'
			account_result = f'{status} Account {i + 1}'
			if user_info:
				account_result += f'\n{user_info}'
			notification_content.append(account_result)
		except Exception as e:
			print(f'[FAILED] Account {i + 1} processing exception: {e}')
			notification_content.append(f'[FAIL] Account {i + 1} exception: {str(e)[:50]}...')

	# 构建通知内容
	summary = [
		'',  # 添加空行
		'[STATS] Check-in result statistics:',
		f'[SUCCESS] Success: {success_count}/{total_count}',
		f'[FAIL] Failed: {total_count - success_count}/{total_count}',
		f':money_with_wings: Total Balance: ${round(total_balance, 2)}',  # 添加总余额显示
	]

	if success_count == total_count:
		summary.append('[SUCCESS] All accounts check-in successful!')
	elif success_count > 0:
		summary.append('[WARN] Some accounts check-in successful')
	else:
		summary.append('[ERROR] All accounts check-in failed')

	time_info = f'[TIME] Execution time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'

	notify_content = '\n\n'.join([time_info, '\n'.join(notification_content), '\n'.join(summary)])

	print(notify_content)

	notify.push_message('AnyRouter Check-in Results', notify_content, msg_type='text')

	# 设置退出码
	sys.exit(0 if success_count > 0 else 1)


if __name__ == '__main__':
	asyncio.run(main())
