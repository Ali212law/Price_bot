#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
iran_news_analyzer4.py — wrapper for iran_news_analyzer3
--------------------------------------------------------
هدف:
  - تحلیل اخبار ایران هر ۳۰ دقیقه (طبق قبل)
  - ارسال پیام به بله: فقط ۱ بار در روز

روش:
  - از iran_news_analyzer3 import می‌کنیم
  - send_message رو با یه نسخه‌ی stateful جایگزین می‌کنیم
  - state در iran_news_notify_state.json روی GitHub

نکته: فایل main اصلی (iran_news_analyzer3.py) دست‌نخورده می‌مونه.
"""

import sys
from datetime import datetime

# Import original module
import iran_news_analyzer3 as v3


STATE_FILE = "iran_news_notify_state.json"


def _load_state():
    """بارگذاری state از GitHub"""
    try:
        data, _ = v3.load_from_github(STATE_FILE)
        if isinstance(data, dict):
            return data
    except Exception as e:
        print(f"  [STATE] load error: {e}")
    return {}


def _save_state(state):
    """ذخیره state روی GitHub"""
    try:
        _, sha = v3.load_from_github(STATE_FILE)
        return v3.save_to_github(STATE_FILE, state, sha)
    except Exception as e:
        print(f"  [STATE] save error: {e}")
        return False


def _should_notify_today():
    """آیا امروز پیام فرستادیم؟"""
    today = datetime.now().date().isoformat()
    state = _load_state()
    last_date = state.get("last_notify_date")
    if last_date == today:
        print(f"  [NOTIFY] already sent today ({today}) — skipping")
        return False
    print(f"  [NOTIFY] new day ({today}) — will send")
    return True


def _mark_notified():
    """ثبت ارسال امروز"""
    today = datetime.now().date().isoformat()
    state = _load_state()
    state["last_notify_date"] = today
    state["last_notify_time"] = datetime.now().isoformat()
    _save_state(state)
    print(f"  [NOTIFY] marked sent for {today}")


# Save original send_message
_original_send_message = v3.send_message


def _send_message_once_per_day(text):
    """
    ارسال پیام فقط ۱ بار در روز.
    تحلیل و ذخیره‌سازی داده همچنان هر ۳۰ دقیقه انجام میشه،
    فقط پیام Bale محدود میشه.
    """
    if _should_notify_today():
        result = _original_send_message(text)
        if result is not None:
            _mark_notified()
        return result
    else:
        print("  [BALE] skipped (already notified today)")
        return None


# Monkey-patch
v3.send_message = _send_message_once_per_day


if __name__ == "__main__":
    print("=" * 60)
    print("  IRAN NEWS ANALYZER v4 (with daily notification)")
    print(f"  Time: {datetime.now().isoformat()}")
    print("=" * 60)
    v3.main()
    print("\n✓ v4 DONE")
