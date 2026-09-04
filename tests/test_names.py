"""Display-name fallbacks."""

from kohakuefda.model.names import Names


def test_get_falls_back_between_chinese_variants_then_english() -> None:
    both = Names(en="Refining Unit", zh_tw="精煉爐", zh_cn="精炼炉")
    assert both.get("zh-TW") == "精煉爐" and both.get("zh-CN") == "精炼炉"
    only_cn = Names(en="Refining Unit", zh_cn="精炼炉")
    assert only_cn.get("zh-TW") == "精炼炉"
    only_tw = Names(en="Refining Unit", zh_tw="精煉爐")
    assert only_tw.get("zh-CN") == "精煉爐"
    assert Names(en="Refining Unit").get("zh-TW") == "Refining Unit"
