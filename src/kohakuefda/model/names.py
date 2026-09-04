"""Display names in the three supported languages."""

from typing import Literal

from kohakuefda.model.base import EfdaModel

Lang = Literal["en", "zh-TW", "zh-CN"]
LANGS: tuple[Lang, ...] = ("en", "zh-TW", "zh-CN")


class Names(EfdaModel):
    """English, Traditional Chinese and Simplified Chinese display names."""

    en: str
    zh_tw: str = ""
    zh_cn: str = ""

    def get(self, lang: Lang) -> str:
        """Name in ``lang``, falling back to English when a translation is empty."""
        match lang:
            case "zh-TW":
                return self.zh_tw or self.zh_cn or self.en
            case "zh-CN":
                return self.zh_cn or self.zh_tw or self.en
            case _:
                return self.en
