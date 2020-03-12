# Copyright 2020; Raja Tomar
# See license for more details
import logging
import threading
import contextlib
import socket

import requests
from requests.exceptions import RequestException
from requests.structures import CaseInsensitiveDict
from six import integer_types
from six.moves.urllib.parse import urlsplit
from six.moves.urllib.parse import urlunsplit
from six.moves.urllib.robotparser import RobotFileParser

from .__version__ import __title__
from .__version__ import __version__

logger = logging.getLogger(__name__)


class RobotsTxtDisallowed(RequestException):
    """Access to requested url disallowed by the robots.txt rules."""


def default_headers():
    """
    :rtype: requests.structures.CaseInsensitiveDict
    """
    return CaseInsensitiveDict({
        'User-Agent': '%s/%s' % (__title__, __version__),
        'Accept-Encoding': ', '.join(('gzip', 'deflate')),
        'Accept': '*/*',
        'Connection': 'keep-alive',
    })


def check_connection(host=None, port=None, timeout=None):
    """Checks whether internet connection is available.

    :param host: dns host address to lookup in.
    :param port: port of the server
    :param timeout: socket timeout time in seconds
    :rtype: bool
    :return: True if available False otherwise
    """
    if not host:
        host = '8.8.8.8'
    if not port:
        port = 53

    #: Family and Type will be default
    with contextlib.closing(socket.socket()) as sock:
        sock.settimeout(timeout)
        with contextlib.suppress(socket.error):
            sock.connect((host, port))
            return True
        return False


class Session(requests.Session):
    """
    Caching Session object which consults robots.txt before accessing a resource.
    You can disable the robots.txt rules by using method `.set_robots_txt`.
    """

    def __init__(self):
        super(Session, self).__init__()
        self.headers = default_headers()
        self.delay = 0.1
        self.waiter = threading.Event()
        self.obey_robots_txt = True
        self.robots_registry = {}
        self.logger = logger.getChild(self.__class__.__name__)

    def enable_http_cache(self):
        try:
            import cachecontrol
        except ImportError:
            raise ImportError(
                "cachecontrol module is not installed."
                " Install it like from pip: $ pip install cachecontrol"
            )
        self.mount('https://', cachecontrol.CacheControlAdapter())
        self.mount('http://', cachecontrol.CacheControlAdapter())

    def set_obey_robots_txt(self, b):
        """Set whether to follow the robots.txt rules or not.
        """
        self.obey_robots_txt = bool(b)
        self.logger.debug('Set obey_robots_txt to [%r] for [%r]' % (b, self))

    #: backward compatibility
    def set_bypass(self, b):
        self.set_obey_robots_txt(not b)

    def load_rules_from_url(self, robots_url, timeout=None):
        """
        Manually load the robots.txt file from the server.
        :param robots_url: url address of the text file to load.
        :param timeout: requests timeout
        :return: loaded rules or None if failed.
        """
        _parser = RobotFileParser()
        try:
            req = requests.Request(
                method='GET',
                url=robots_url,
                headers=self.headers,
                auth=self.auth,
                cookies=self.cookies,
                hooks=self.hooks
            )
            prep = req.prepare()
            send_kwargs = {
                'stream': False,
                'timeout': timeout,
                'verify': self.verify,
                'cert': self.cert,
                'proxies': self.proxies,
                'allow_redirects': True,
            }
            f = super(Session, self).send(prep, **send_kwargs)
            f.raise_for_status()
            self.cookies.update(f.cookies)
        except requests.exceptions.HTTPError as err:
            code = err.response.status_code
            if code in (401, 403):
                _parser.disallow_all = True
            elif 400 <= code < 500:
                _parser.allow_all = True
        except requests.exceptions.ConnectionError:
            _parser.allow_all = True
        else:
            _parser.parse(f.text.splitlines())
        self.robots_registry[robots_url] = _parser
        return _parser

    def is_allowed(self, request, timeout=None):
        #: if set to not follow the robots.txt
        if not self.obey_robots_txt:
            return True

        s, n, p, q, f = urlsplit(request.url)
        robots_url = urlunsplit((s, n, 'robots.txt', None, None))
        try:
            access_rules = self.robots_registry[robots_url]
        except KeyError:
            access_rules = self.load_rules_from_url(robots_url, timeout)
        if access_rules is None:  # error - everybody welcome
            return True
        user_agent = request.headers.get('User-Agent', '*')
        return access_rules.can_fetch(user_agent, request.url)

    def send(self, request, **kwargs):
        if not isinstance(request, requests.PreparedRequest):
            raise ValueError('You can only send PreparedRequests.')
        if not self.is_allowed(request, kwargs.get('timeout', None)):
            self.logger.error("Access to [%r] disallowed by the robots.txt rules.", request.url)
            raise RobotsTxtDisallowed("Access to [%r] disallowed by the robots.txt rules." % request.url)
        self.logger.info('[%s] [%s]' % (request.method, request.url))
        if isinstance(self.delay, integer_types):
            self.logger.debug('Waiting on [%s] request until [%d]' % (request.url, self.delay))
            self.waiter.wait(self.delay)
        return super(Session, self).send(request, **kwargs)

    @classmethod
    def from_config(cls, config):
        """Creates a new instance of Session object using the config object."""
        ans = cls()
        ans.headers = config.get('http_headers', default_headers())
        ans.obey_robots_txt = not config.get('bypass_robots')
        ans.delay = config.get('delay')
        if config.get('http_cache'):
            ans.enable_http_cache()
        return ans
