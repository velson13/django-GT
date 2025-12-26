# sef_http.py
import requests
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager


class IPv4Adapter(HTTPAdapter):
    def init_poolmanager(self, connections, maxsize, block=False, **kwargs):
        self.poolmanager = PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            source_address=("0.0.0.0", 0),
            **kwargs,
        )


# one shared session (connection pooling)
_sef_session = requests.Session()
_sef_session.mount("https://", IPv4Adapter())


def sef_get(url, **kwargs):
    return _sef_session.get(url, **kwargs)
