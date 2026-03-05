# -*- coding: utf-8 -*-
"""
代理:https://jahttp.zhimaruanjian.com/getapi/

@desc: adata 请求工具类
@author: 1nchaos
@time:2023/3/30
@log: 封装请求次数
"""

import threading
import time
from urllib.parse import urlparse
from collections import defaultdict

import requests


class SunProxy(object):
    _data = {}
    _instance_lock = threading.Lock()

    def __init__(self):
        pass

    def __new__(cls, *args, **kwargs):
        if not hasattr(SunProxy, "_instance"):
            with SunProxy._instance_lock:
                if not hasattr(SunProxy, "_instance"):
                    SunProxy._instance = object.__new__(cls)

    @classmethod
    def set(cls, key, value):
        cls._data[key] = value

    @classmethod
    def get(cls, key):
        return cls._data.get(key)

    @classmethod
    def delete(cls, key):
        if key in cls._data:
            del cls._data[key]


class RateLimiter:
    """
    频率限制器：按域名限制请求频率
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self):
        # 每个域名的请求时间戳列表 {domain: [timestamp1, timestamp2, ...]}
        self._domain_requests = defaultdict(list)
        # 每个域名的频率限制 {domain: max_requests_per_minute}
        self._domain_limits = defaultdict(lambda: 30)
        # 默认频率限制
        self._default_limit = 30
        self._lock = threading.Lock()

    def set_rate_limit(self, domain: str = None, max_requests_per_minute: int = 30):
        """
        设置频率限制
        :param domain: 域名，如 'api.example.com'；为 None 时设置全局默认值
        :param max_requests_per_minute: 每分钟最大请求数
        """
        if domain is None:
            self._default_limit = max_requests_per_minute
        else:
            self._domain_limits[domain] = max_requests_per_minute

    def get_rate_limit(self, domain: str) -> int:
        """获取指定域名的频率限制"""
        return self._domain_limits.get(domain, self._default_limit)

    def acquire(self, url: str):
        """
        获取请求许可，如果超过频率限制则等待
        :param url: 请求的 URL
        """
        domain = urlparse(url).netloc
        if not domain:
            return

        limit = self.get_rate_limit(domain)
        window = 60  # 60秒窗口

        with self._lock:
            now = time.time()
            # 清理窗口外的旧记录
            self._domain_requests[domain] = [
                ts for ts in self._domain_requests[domain]
                if now - ts < window
            ]

            # 如果已达到限制，计算需要等待的时间
            if len(self._domain_requests[domain]) >= limit:
                oldest_ts = self._domain_requests[domain][0]
                wait_time = window - (now - oldest_ts)
                if wait_time > 0:
                    time.sleep(wait_time)
                    now = time.time()
                    # 再次清理
                    self._domain_requests[domain] = [
                        ts for ts in self._domain_requests[domain]
                        if now - ts < window
                    ]

            # 记录当前请求时间戳
            self._domain_requests[domain].append(now)


class SunRequests(object):
    def __init__(self, sun_proxy: SunProxy = None) -> None:
        super().__init__()
        self.sun_proxy = sun_proxy
        self._rate_limiter = RateLimiter()

    def set_rate_limit(self, domain: str = None, max_requests_per_minute: int = 30):
        """
        设置频率限制
        :param domain: 域名，如 'api.example.com'；为 None 时设置全局默认值
        :param max_requests_per_minute: 每分钟最大请求数，默认30
        """
        self._rate_limiter.set_rate_limit(domain, max_requests_per_minute)

    def request(self, method='get', url=None, times=3, retry_wait_time=1588, proxies=None, wait_time=None,
                rate_limit_domain: str = None, rate_limit: int = None, **kwargs):
        """
        简单封装的请求，参考requests，增加循环次数和次数之间的等待时间
        :param proxies: 代理配置
        :param method: 请求方法： get；post
        :param url: url
        :param times: 次数，int
        :param retry_wait_time: 重试等待时间，毫秒
        :param wait_time: 等待时间：毫秒；表示每个请求的间隔时间，在请求之前等待sleep，主要用于防止请求太频繁的限制。
        :param rate_limit_domain: 指定频率限制的域名，为 None 时从 url 自动提取
        :param rate_limit: 当前请求的频率限制（每分钟请求数），为 None 时使用全局设置
        :param kwargs: 其它 requests 参数，用法相同
        :return: res
        """
        # 0. 频率限制
        if rate_limit is not None and url:
            domain = rate_limit_domain or urlparse(url).netloc
            original_limit = self._rate_limiter.get_rate_limit(domain)
            self._rate_limiter.set_rate_limit(domain, rate_limit)
            self._rate_limiter.acquire(url)
            # 恢复原来的限制设置
            self._rate_limiter.set_rate_limit(domain, original_limit)
        elif url:
            self._rate_limiter.acquire(url)

        # 1. 获取设置代理
        proxies = self.__get_proxies(proxies)
        # 2. 请求数据结果
        res = None
        for i in range(times):
            if wait_time:
                time.sleep(wait_time / 1000)
            res = requests.request(method=method, url=url, proxies=proxies, **kwargs)
            if res.status_code in (200, 404):
                return res
            time.sleep(retry_wait_time / 1000)
            if i == times - 1:
                return res
        return res

    def __get_proxies(self, proxies):
        """
        获取代理配置
        """
        if proxies is None:
            proxies = {}
        is_proxy = SunProxy.get('is_proxy')
        ip = SunProxy.get('ip')
        proxy_url = SunProxy.get('proxy_url')
        if not ip and is_proxy and proxy_url:
            ip = requests.get(url=proxy_url).text.replace('\r\n', '') \
                .replace('\r', '').replace('\n', '').replace('\t', '')
        if is_proxy and ip:
            proxies = {'https': f"http://{ip}", 'http': f"http://{ip}"}
        return proxies


sun_requests = SunRequests()
