"""Small synchronous SIATA HTTP client with bounded retries."""

import time

import httpx


class SiataClient(httpx.Client):
    def __init__(
        self,
        *,
        timeout: float = 12.0,
        headers: dict | None = None,
        transport_retries: int = 2,
        retry_attempts: int = 3,
    ):
        super().__init__(
            headers=headers or {},
            timeout=timeout,
            follow_redirects=True,
            transport=httpx.HTTPTransport(retries=max(0, transport_retries)),
        )
        self.retry_attempts = max(1, retry_attempts)

    def request(self, method: str, url: str, **kwargs):
        for attempt in range(self.retry_attempts):
            response = super().request(method, url, **kwargs)
            if response.status_code not in (429, 500, 502, 503, 504) or attempt == self.retry_attempts - 1:
                response.raise_for_status()
                return response
            try:
                delay = min(max(float(response.headers.get("Retry-After", 0)), 0.0), 4.0)
            except ValueError:
                delay = 0
            time.sleep(delay or 0.25 * (2 ** attempt))
