import asyncio
import time
from typing import Dict, Any, List
import httpx


async def check_single_website(client: httpx.AsyncClient, site: Dict[str, Any]) -> Dict[str, Any]:
    url = site.get("url", "")
    expected_code = int(site.get("expected_code", 200))
    timeout = float(site.get("timeout_seconds", 10))
    site_id = site.get("id", url)
    name = site.get("name", url)

    start_time = time.monotonic()
    result = {
        "id": site_id,
        "name": name,
        "url": url,
        "is_up": False,
        "status_code": 0,
        "response_time_ms": 0.0,
        "error": None,
        "checked_at": time.time()
    }

    if not url:
        result["error"] = "Empty URL"
        return result

    try:
        response = await client.get(url, timeout=timeout, follow_redirects=True)
        elapsed_ms = round((time.monotonic() - start_time) * 1000, 2)
        result["response_time_ms"] = elapsed_ms
        result["status_code"] = response.status_code

        if response.status_code == expected_code or (expected_code == 200 and 200 <= response.status_code < 400):
            result["is_up"] = True
        else:
            result["is_up"] = False
            result["error"] = f"Unexpected status code: {response.status_code} (Expected {expected_code})"
    except httpx.TimeoutException:
        result["error"] = f"Connection timed out (> {timeout}s)"
    except httpx.ConnectError:
        result["error"] = "Failed to establish connection (Port closed or Host unreachable)"
    except Exception as e:
        result["error"] = str(e)

    return result


async def check_all_websites(sites: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not sites:
        return []

    limits = httpx.Limits(max_keepalive_connections=10, max_connections=20)
    async with httpx.AsyncClient(limits=limits, verify=False) as client:
        tasks = [check_single_website(client, site) for site in sites]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        return results

