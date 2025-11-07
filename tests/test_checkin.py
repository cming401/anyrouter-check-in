import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# 添加项目根目录到 PATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import checkin


@pytest.mark.asyncio
async def test_check_in_account_without_waf_cookies():
	"""测试当无法获取 WAF cookies 时仍然尝试获取用户余额"""
	account_info = {'cookies': {'session': 'test_session'}, 'api_user': '12345'}

	# Mock get_waf_cookies_with_playwright to return None (simulating failure)
	with patch('checkin.get_waf_cookies_with_playwright', new_callable=AsyncMock) as mock_get_waf:
		mock_get_waf.return_value = None

		# Mock httpx.Client
		with patch('checkin.httpx.Client') as mock_client_class:
			mock_client = MagicMock()
			mock_client_class.return_value = mock_client
			mock_client.__enter__ = MagicMock(return_value=mock_client)
			mock_client.__exit__ = MagicMock(return_value=False)

			# Mock the user info response
			mock_user_response = MagicMock()
			mock_user_response.status_code = 200
			mock_user_response.json.return_value = {
				'success': True,
				'data': {'quota': 1000000, 'used_quota': 500000},
			}

			# Mock the check-in response
			mock_checkin_response = MagicMock()
			mock_checkin_response.status_code = 200
			mock_checkin_response.json.return_value = {'ret': 1}

			# Set up the mock to return different responses for different calls
			mock_client.get.return_value = mock_user_response
			mock_client.post.return_value = mock_checkin_response

			# Run the check-in function
			success, user_info, balance = await checkin.check_in_account(account_info, 0)

			# Verify the function didn't fail early
			assert mock_client.get.called, 'Should attempt to get user info even without WAF cookies'
			assert mock_client.post.called, 'Should attempt check-in even without WAF cookies'

			# Verify user cookies were used
			mock_client.cookies.update.assert_called()
			cookies_arg = mock_client.cookies.update.call_args[0][0]
			assert 'session' in cookies_arg, 'User cookies should be present'


@pytest.mark.asyncio
async def test_check_in_account_with_waf_cookies():
	"""测试当成功获取 WAF cookies 时的正常流程"""
	account_info = {'cookies': {'session': 'test_session'}, 'api_user': '12345'}

	# Mock get_waf_cookies_with_playwright to return WAF cookies
	waf_cookies = {'acw_tc': 'test_acw_tc', 'cdn_sec_tc': 'test_cdn_sec_tc', 'acw_sc__v2': 'test_acw_sc__v2'}

	with patch('checkin.get_waf_cookies_with_playwright', new_callable=AsyncMock) as mock_get_waf:
		mock_get_waf.return_value = waf_cookies

		# Mock httpx.Client
		with patch('checkin.httpx.Client') as mock_client_class:
			mock_client = MagicMock()
			mock_client_class.return_value = mock_client
			mock_client.__enter__ = MagicMock(return_value=mock_client)
			mock_client.__exit__ = MagicMock(return_value=False)

			# Mock the user info response
			mock_user_response = MagicMock()
			mock_user_response.status_code = 200
			mock_user_response.json.return_value = {
				'success': True,
				'data': {'quota': 1000000, 'used_quota': 500000},
			}

			# Mock the check-in response
			mock_checkin_response = MagicMock()
			mock_checkin_response.status_code = 200
			mock_checkin_response.json.return_value = {'ret': 1}

			# Set up the mock to return different responses for different calls
			mock_client.get.return_value = mock_user_response
			mock_client.post.return_value = mock_checkin_response

			# Run the check-in function
			success, user_info, balance = await checkin.check_in_account(account_info, 0)

			# Verify both user and WAF cookies were used
			mock_client.cookies.update.assert_called()
			cookies_arg = mock_client.cookies.update.call_args[0][0]
			assert 'session' in cookies_arg, 'User cookies should be present'
			assert 'acw_tc' in cookies_arg, 'WAF cookies should be present'
			assert 'cdn_sec_tc' in cookies_arg, 'WAF cookies should be present'
			assert 'acw_sc__v2' in cookies_arg, 'WAF cookies should be present'


@pytest.mark.asyncio
async def test_check_in_account_balance_display_without_waf():
	"""测试当 WAF cookies 失败时，仍然显示余额信息"""
	account_info = {'cookies': {'session': 'test_session'}, 'api_user': '12345'}

	with patch('checkin.get_waf_cookies_with_playwright', new_callable=AsyncMock) as mock_get_waf:
		mock_get_waf.return_value = None

		with patch('checkin.httpx.Client') as mock_client_class:
			mock_client = MagicMock()
			mock_client_class.return_value = mock_client
			mock_client.__enter__ = MagicMock(return_value=mock_client)
			mock_client.__exit__ = MagicMock(return_value=False)

			# Mock the user info response with balance data
			mock_user_response = MagicMock()
			mock_user_response.status_code = 200
			mock_user_response.json.return_value = {
				'success': True,
				'data': {'quota': 2500000, 'used_quota': 1000000},  # $5 balance, $2 used
			}

			# Mock the check-in response
			mock_checkin_response = MagicMock()
			mock_checkin_response.status_code = 200
			mock_checkin_response.json.return_value = {'ret': 1}

			mock_client.get.return_value = mock_user_response
			mock_client.post.return_value = mock_checkin_response

			# Run the check-in function
			success, user_info, balance = await checkin.check_in_account(account_info, 0)

			# Verify balance information is returned even without WAF cookies
			assert balance == 5.0, 'Balance should be calculated correctly'
			assert user_info is not None, 'User info should be returned'
			assert '$5' in user_info, 'Balance should be in user info string'
