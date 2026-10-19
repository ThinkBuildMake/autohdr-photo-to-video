import pytest

from app.providers import video_api
from app.providers.errors import ProviderError


def test_allowed_lengths_come_from_the_model_list_and_are_cached(videos_api):
    assert video_api.allowed_lengths("google/veo-3.1") == [4.0, 6.0, 8.0]
    assert video_api.allowed_lengths("google/veo-3.1") == [4.0, 6.0, 8.0]

    assert videos_api.count("GET", "/videos/models") == 1


def test_price_per_second_and_missing_price(videos_api):
    assert video_api.price_per_second("google/veo-3.1") == 0.20
    assert video_api.price_per_second("bytedance/seedance-2.0") is None
    assert video_api.allowed_lengths("bytedance/seedance-2.0")[0] == 4.0


def test_unlisted_model_is_bad_response(videos_api):
    with pytest.raises(ProviderError) as caught:
        video_api.allowed_lengths("nobody/model")
    assert caught.value.kind == "bad_response"


def test_unreachable_list_is_an_error_and_not_cached(videos_api):
    import httpx

    videos_api.models = lambda request: httpx.Response(500, json={"error": {"message": "down"}})
    with pytest.raises(ProviderError) as caught:
        video_api.allowed_lengths("google/veo-3.1")
    assert caught.value.kind == "failed"

    videos_api.models = lambda request: httpx.Response(200, json={"data": []})
    with pytest.raises(ProviderError):
        video_api.allowed_lengths("google/veo-3.1")
    assert videos_api.count("GET", "/videos/models") == 2
