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


class RateLimiter(object):
    """
    频率限制器，控制每个域名的请求频率
    """
    _instance_lock = threading.Lock()
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not hasattr(RateLimiter, "_instance"):
            with RateLimiter._instance_lock:
                if not hasattr(RateLimiter, "_instance"):
                    RateLimiter._instance = object.__new__(cls)
        return RateLimiter._instance

    def __init__(self):
        self.lock = threading.Lock()
        self.default_limit = 30
        self.domain_limits = {}
        self.request_records = {}

    def set_default_limit(self, limit):
        """
        设置默认的请求频率限制
        :param limit: 每分钟的请求次数
        """
        with self.lock:
            self.default_limit = limit

    def set_domain_limit(self, domain, limit):
        """
        设置特定域名的请求频率限制
        :param domain: 域名
        :param limit: 每分钟的请求次数
        """
        with self.lock:
            self.domain_limits[domain] = limit

    def _get_domain(self, url):
        """
        从URL中提取域名
        """
        parsed = urlparse(url)
        return parsed.netloc

    def _clean_old_records(self, domain, current_time):
        """
        清理超过1分钟的请求记录
        """
        if domain not in self.request_records:
            return
        cutoff_time = current_time - 60
        self.request_records[domain] = [t for t in self.request_records[domain] if t > cutoff_time]

    def acquire(self, url):
        """
        获取请求权限，如果超过频率限制则等待
        :param url: 请求的URL
        """
        domain = self._get_domain(url)
        current_time = time.time()

        with self.lock:
            self._clean_old_records(domain, current_time)
            
            if domain not in self.request_records:
                self.request_records[domain] = []
            
            limit = self.domain_limits.get(domain, self.default_limit)
            
            while len(self.request_records[domain]) >= limit:
                oldest_time = min(self.request_records[domain])
                wait_time = oldest_time + 60 - current_time
                if wait_time > 0:
                    time.sleep(wait_time)
                current_time = time.time()
                self._clean_old_records(domain, current_time)
            
            self.request_records[domain].append(current_time)


class SunRequests(object):
    def __init__(self, sun_proxy: SunProxy = None) -> None:
        super().__init__()
        self.sun_proxy = sun_proxy
        self.rate_limiter = RateLimiter()

    def request(self, method='get', url=None, times=3, retry_wait_time=1588, proxies=None, wait_time=None, **kwargs):
        """
        简单封装的请求，参考requests，增加循环次数和次数之间的等待时间
        :param proxies: 代理配置
        :param method: 请求方法： get；post
        :param url: url
        :param times: 次数，int
        :param retry_wait_time: 重试等待时间，毫秒
        :param wait_time: 等待时间：毫秒；表示每个请求的间隔时间，在请求之前等待sleep，主要用于防止请求太频繁的限制。
        :param kwargs: 其它 requests 参数，用法相同
        :return: res
        """
        if url:
            self.rate_limiter.acquire(url)
        
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

    def set_rate_limit(self, limit):
        """
        设置默认的频率限制
        :param limit: 每分钟的请求次数
        """
        self.rate_limiter.set_default_limit(limit)

    def set_domain_rate_limit(self, domain, limit):
        """
        设置特定域名的频率限制
        :param domain: 域名
        :param limit: 每分钟的请求次数
        """
        self.rate_limiter.set_domain_limit(domain, limit)


sun_requests = SunRequests()
