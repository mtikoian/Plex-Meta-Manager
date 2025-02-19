import requests, time
from datetime import datetime
from lxml.etree import ParserError
from modules import util
from modules.util import Failed
from retrying import retry

logger = util.logger

builders = ["tvdb_list", "tvdb_list_details", "tvdb_movie", "tvdb_movie_details", "tvdb_show", "tvdb_show_details"]
base_url = "https://www.thetvdb.com"
alt_url = "https://thetvdb.com"
urls = {
    "list": f"{base_url}/lists/", "alt_list": f"{alt_url}/lists/",
    "series": f"{base_url}/series/", "alt_series": f"{alt_url}/series/",
    "movies": f"{base_url}/movies/", "alt_movies": f"{alt_url}/movies/",
    "series_id": f"{base_url}/dereferrer/series/", "movie_id": f"{base_url}/dereferrer/movie/"
}
language_translation = {
    "ab": "abk", "aa": "aar", "af": "afr", "ak": "aka", "sq": "sqi", "am": "amh", "ar": "ara", "an": "arg", "hy": "hye",
    "as": "asm", "av": "ava", "ae": "ave", "ay": "aym", "az": "aze", "bm": "bam", "ba": "bak", "eu": "eus", "be": "bel",
    "bn": "ben", "bi": "bis", "bs": "bos", "br": "bre", "bg": "bul", "my": "mya", "ca": "cat", "ch": "cha", "ce": "che",
    "ny": "nya", "zh": "zho", "cv": "chv", "kw": "cor", "co": "cos", "cr": "cre", "hr": "hrv", "cs": "ces", "da": "dan",
    "dv": "div", "nl": "nld", "dz": "dzo", "en": "eng", "eo": "epo", "et": "est", "ee": "ewe", "fo": "fao", "fj": "fij",
    "fi": "fin", "fr": "fra", "ff": "ful", "gl": "glg", "ka": "kat", "de": "deu", "el": "ell", "gn": "grn", "gu": "guj",
    "ht": "hat", "ha": "hau", "he": "heb", "hz": "her", "hi": "hin", "ho": "hmo", "hu": "hun", "ia": "ina", "id": "ind",
    "ie": "ile", "ga": "gle", "ig": "ibo", "ik": "ipk", "io": "ido", "is": "isl", "it": "ita", "iu": "iku", "ja": "jpn",
    "jv": "jav", "kl": "kal", "kn": "kan", "kr": "kau", "ks": "kas", "kk": "kaz", "km": "khm", "ki": "kik", "rw": "kin",
    "ky": "kir", "kv": "kom", "kg": "kon", "ko": "kor", "ku": "kur", "kj": "kua", "la": "lat", "lb": "ltz", "lg": "lug",
    "li": "lim", "ln": "lin", "lo": "lao", "lt": "lit", "lu": "lub", "lv": "lav", "gv": "glv", "mk": "mkd", "mg": "mlg",
    "ms": "msa", "ml": "mal", "mt": "mlt", "mi": "mri", "mr": "mar", "mh": "mah", "mn": "mon", "na": "nau", "nv": "nav",
    "nd": "nde", "ne": "nep", "ng": "ndo", "nb": "nob", "nn": "nno", "no": "nor", "ii": "iii", "nr": "nbl", "oc": "oci",
    "oj": "oji", "cu": "chu", "om": "orm", "or": "ori", "os": "oss", "pa": "pan", "pi": "pli", "fa": "fas", "pl": "pol",
    "ps": "pus", "pt": "por", "qu": "que", "rm": "roh", "rn": "run", "ro": "ron", "ru": "rus", "sa": "san", "sc": "srd",
    "sd": "snd", "se": "sme", "sm": "smo", "sg": "sag", "sr": "srp", "gd": "gla", "sn": "sna", "si": "sin", "sk": "slk",
    "sl": "slv", "so": "som", "st": "sot", "es": "spa", "su": "sun", "sw": "swa", "ss": "ssw", "sv": "swe", "ta": "tam",
    "te": "tel", "tg": "tgk", "th": "tha", "ti": "tir", "bo": "bod", "tk": "tuk", "tl": "tgl", "tn": "tsn", "to": "ton",
    "tr": "tur", "ts": "tso", "tt": "tat", "tw": "twi", "ty": "tah", "ug": "uig", "uk": "ukr", "ur": "urd", "uz": "uzb",
    "ve": "ven", "vi": "vie", "vo": "vol", "wa": "wln", "cy": "cym", "wo": "wol", "fy": "fry", "xh": "xho", "yi": "yid",
    "yo": "yor", "za": "zha", "zu": "zul"}

class TVDbObj:
    def __init__(self, tvdb, tvdb_id, is_movie=False, ignore_cache=False):
        self._tvdb = tvdb
        self.tvdb_id = tvdb_id
        self.is_movie = is_movie
        self.ignore_cache = ignore_cache
        expired = None
        data = None
        if self._tvdb.config.Cache and not ignore_cache:
            data, expired = self._tvdb.config.Cache.query_tvdb(tvdb_id, is_movie, self._tvdb.expiration)
        if expired or not data:
            data = self._tvdb.get_request(f"{urls['movie_id' if is_movie else 'series_id']}{tvdb_id}")

        def parse_page(xpath, is_list=False):
            parse_results = data.xpath(xpath)
            if len(parse_results) > 0:
                parse_results = [r.strip() for r in parse_results if len(r) > 0]
            return parse_results if is_list else parse_results[0] if len(parse_results) > 0 else None

        def parse_title_summary(lang=None):
            place = "//div[@class='change_translation_text' and "
            place += f"@data-language='{lang}']" if lang else "not(@style='display:none')]"
            return parse_page(f"{place}/@data-title"), parse_page(f"{place}/p/text()[normalize-space()]")

        if isinstance(data, dict):
            self.title = data["title"]
            self.summary = data["summary"]
            self.poster_url = data["poster_url"]
            self.background_url = data["background_url"]
            self.release_date = data["release_date"]
            self.genres = data["genres"].split("|")
        else:
            self.title, self.summary = parse_title_summary(lang=self._tvdb.language)
            if not self.title and self._tvdb.language in language_translation:
                self.title, self.summary = parse_title_summary(lang=language_translation[self._tvdb.language])
            if not self.title:
                self.title, self.summary = parse_title_summary()
            if not self.title:
                raise Failed(f"TVDb Error: Name not found from TVDb ID: {self.tvdb_id}")

            self.poster_url = parse_page("(//h2[@class='mt-4' and text()='Posters']/following::div/a/@href)[1]")
            self.background_url = parse_page("(//h2[@class='mt-4' and text()='Backgrounds']/following::div/a/@href)[1]")
            if is_movie:
                released = parse_page("//strong[text()='Released']/parent::li/span/text()[normalize-space()]")
            else:
                released = parse_page("//strong[text()='First Aired']/parent::li/span/text()[normalize-space()]")

            try:
                self.release_date = datetime.strptime(released, "%B %d, %Y") if released else released
            except ValueError:
                self.release_date = None

            self.genres = parse_page("//strong[text()='Genres']/parent::li/span/a/text()[normalize-space()]", is_list=True)

        if self._tvdb.config.Cache and not ignore_cache:
            self._tvdb.config.Cache.update_tvdb(expired, self, self._tvdb.expiration)

class TVDb:
    def __init__(self, config, tvdb_language, expiration):
        self.config = config
        self.language = tvdb_language
        self.expiration = expiration

    def get_tvdb_obj(self, tvdb_url, is_movie=False):
        tvdb_id, _, _ = self.get_id_from_url(tvdb_url, is_movie=is_movie)
        return TVDbObj(self, tvdb_id, is_movie=is_movie)

    def get_list_description(self, tvdb_url):
        response = self.config.get_html(tvdb_url, headers=util.header(self.language))
        description = response.xpath("//div[@class='block']/div[not(@style='display:none')]/p/text()")
        return description[0] if len(description) > 0 and len(description[0]) > 0 else ""

    @retry(stop_max_attempt_number=6, wait_fixed=10000, retry_on_exception=util.retry_if_not_failed)
    def get_request(self, tvdb_url):
        return self.config.get_html(tvdb_url, headers=util.header(self.language))

    def get_id_from_url(self, tvdb_url, is_movie=False, ignore_cache=False):
        try:
            if not is_movie:
                return int(tvdb_url), None, None
            else:
                tvdb_url = f"{urls['movie_id']}{int(tvdb_url)}"
        except ValueError:
            pass
        tvdb_url = tvdb_url.strip()
        if tvdb_url.startswith((urls["series"], urls["alt_series"], urls["series_id"])):
            media_type = "Series"
        elif tvdb_url.startswith((urls["movies"], urls["alt_movies"], urls["movie_id"])):
            media_type = "Movie"
        else:
            raise Failed(f"TVDb Error: {tvdb_url} must begin with {urls['movies']} or {urls['series']}")
        expired = None
        tvdb_id = None
        if self.config.Cache and not ignore_cache:
            tvdb_id, expired = self.config.Cache.query_tvdb_map(tvdb_url, self.expiration)
        if tvdb_id and not expired and not is_movie:
            return tvdb_id, None, None
        logger.trace(f"URL: {tvdb_url}")
        try:
            response = self.get_request(tvdb_url)
        except ParserError:
            raise Failed(f"TVDb Error: Could not parse {tvdb_url}")
        results = response.xpath(f"//*[text()='TheTVDB.com {media_type} ID']/parent::node()/span/text()")
        if len(results) > 0:
            tvdb_id = int(results[0])
            tmdb_id = None
            imdb_id = None
            if media_type == "Movie":
                results = response.xpath("//*[text()='TheMovieDB.com']/@href")
                if len(results) > 0:
                    try:
                        tmdb_id = util.regex_first_int(results[0], "TMDb ID")
                    except Failed:
                        pass
                results = response.xpath("//*[text()='IMDB']/@href")
                if len(results) > 0:
                    try:
                        imdb_id = util.get_id_from_imdb_url(results[0])
                    except Failed:
                        pass
                if tmdb_id is None and imdb_id is None:
                    raise Failed(f"TVDb Error: No TMDb ID or IMDb ID found")
            if self.config.Cache and not ignore_cache:
                self.config.Cache.update_tvdb_map(expired, tvdb_url, tvdb_id, self.expiration)
            return tvdb_id, tmdb_id, imdb_id
        elif tvdb_url.startswith(urls["movie_id"]):
            err_text = f"using TVDb Movie ID: {tvdb_url[len(urls['movie_id']):]}"
        elif tvdb_url.startswith(urls["series_id"]):
            err_text = f"using TVDb Series ID: {tvdb_url[len(urls['series_id']):]}"
        else:
            err_text = f"ID at the URL {tvdb_url}"
        raise Failed(f"TVDb Error: Could not find a TVDb {media_type} {err_text}")

    def _ids_from_url(self, tvdb_url):
        ids = []
        tvdb_url = tvdb_url.strip()
        logger.trace(f"URL: {tvdb_url}")
        if tvdb_url.startswith((urls["list"], urls["alt_list"])):
            try:
                response = self.config.get_html(tvdb_url, headers=util.header(self.language))
                items = response.xpath("//div[@class='row']/div/div[@class='row']/div/h3/a")
                for item in items:
                    title = item.xpath("text()")[0]
                    item_url = item.xpath("@href")[0]
                    if item_url.startswith("/series/"):
                        try:
                            tvdb_id, _, _ = self.get_id_from_url(f"{base_url}{item_url}")
                            if tvdb_id:
                                ids.append((tvdb_id, "tvdb"))
                        except Failed as e:
                            logger.error(f"{e} for series {title}")
                    elif item_url.startswith("/movies/"):
                        try:
                            _, tmdb_id, imdb_id = self.get_id_from_url(f"{base_url}{item_url}")
                            if tmdb_id:
                                ids.append((tmdb_id, "tmdb"))
                            elif imdb_id:
                                ids.append((imdb_id, "imdb"))
                        except Failed as e:
                            logger.error(f"{e} for movie {title}")
                    else:
                        logger.error(f"TVDb Error: Skipping Movie: {title}")
                    time.sleep(2)
                if len(ids) > 0:
                    return ids
                raise Failed(f"TVDb Error: No TVDb IDs found at {tvdb_url}")
            except requests.exceptions.MissingSchema:
                logger.stacktrace()
                raise Failed(f"TVDb Error: URL Lookup Failed for {tvdb_url}")
        else:
            raise Failed(f"TVDb Error: {tvdb_url} must begin with {urls['list']}")

    def get_tvdb_ids(self, method, data):
        if method == "tvdb_show":
            logger.info(f"Processing TVDb Show: {data}")
            ids = []
            try:
                tvdb_id, _, _ = self.get_id_from_url(data)
                if tvdb_id:
                    ids.append((tvdb_id, "tvdb"))
            except Failed as e:
                logger.error(e)
            return ids
        elif method == "tvdb_movie":
            logger.info(f"Processing TVDb Movie: {data}")
            ids = []
            try:
                _, tmdb_id, imdb_id = self.get_id_from_url(data)
                if tmdb_id:
                    ids.append((tmdb_id, "tmdb"))
                elif imdb_id:
                    ids.append((imdb_id, "imdb"))
            except Failed as e:
                logger.error(e)
            return ids
        elif method == "tvdb_list":
            logger.info(f"Processing TVDb List: {data}")
            return self._ids_from_url(data)
        else:
            raise Failed(f"TVDb Error: Method {method} not supported")
