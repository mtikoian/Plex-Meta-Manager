import logging, time
from modules import util
from modules.util import Failed

logger = logging.getLogger("Plex Meta Manager")

builders = ["anilist_id", "anilist_popular", "anilist_relations", "anilist_studio", "anilist_top_rated", "anilist_search"]
pretty_names = {"score": "Average Score", "popular": "Popularity"}
attr_translation = {"year": "seasonYear", "adult": "isAdult", "start": "startDate", "end": "endDate", "tag_category": "tagCategory", "score": "averageScore", "min_tag_percent": "minimumTagRank"}
mod_translation = {"": "in", "not": "not_in", "before": "greater", "after": "lesser", "gt": "greater", "gte": "greater", "lt": "lesser", "lte": "lesser"}
mod_searches = [
    "start.before", "start.after", "end.before", "end.after",
    "format", "format.not", "status", "status.not", "genre", "genre.not", "tag", "tag.not", "tag_category", "tag_category.not",
    "episodes.gt", "episodes.gte", "episodes.lt", "episodes.lte", "duration.gt", "duration.gte", "duration.lt", "duration.lte",
    "score.gt", "score.gte", "score.lt", "score.lte", "popularity.gt", "popularity.gte", "popularity.lt", "popularity.lte"
]
no_mod_searches = ["search", "season", "year", "adult", "min_tag_percent", "limit", "sort_by"]
searches = mod_searches + no_mod_searches
search_types = {
    "search": "String", "season": "MediaSeason", "seasonYear": "Int", "isAdult": "Boolean", "minimumTagRank": "Int",
    "startDate": "FuzzyDateInt", "endDate": "FuzzyDateInt", "format": "[MediaFormat]", "status": "[MediaStatus]",
    "genre": "[String]", "tag": "[String]", "tagCategory": "[String]",
    "episodes": "Int", "duration": "Int", "averageScore": "Int", "popularity": "Int"
}
media_season = {"winter": "WINTER", "spring": "SPRING", "summer": "SUMMER", "fall": "FALL"}
media_format = {"tv": "TV", "short": "TV_SHORT", "movie": "MOVIE", "special": "SPECIAL", "ova": "OVA", "ona": "ONA", "music": "MUSIC"}
media_status = {"finished": "FINISHED", "airing": "RELEASING", "not_yet_aired": "NOT_YET_RELEASED", "cancelled": "CANCELLED", "hiatus": "HIATUS"}
base_url = "https://graphql.anilist.co"
tag_query = "query{MediaTagCollection {name, category}}"
genre_query = "query{GenreCollection}"

class AniList:
    def __init__(self, config):
        self.config = config
        self.options = {
            "Tag": {}, "Tag Category": {},
            "Genre": {g.lower().replace(" ", "-"): g for g in self._request(genre_query, {})["data"]["GenreCollection"]},
            "Season": media_season, "Format": media_format, "Status": media_status
        }
        for media_tag in self._request(tag_query, {})["data"]["MediaTagCollection"]:
            self.options["Tag"][media_tag["name"].lower().replace(" ", "-")] = media_tag["name"]
            self.options["Tag Category"][media_tag["category"].lower().replace(" ", "-")] = media_tag["category"]

    def _request(self, query, variables, level=1):
        response = self.config.post(base_url, json={"query": query, "variables": variables})
        json_obj = response.json()
        if "errors" in json_obj:
            if json_obj['errors'][0]['message'] == "Too Many Requests.":
                wait_time = int(response.headers["Retry-After"]) if "Retry-After" in response.headers else 0
                time.sleep(wait_time if wait_time > 0 else 10)
                if level < 6:
                    return self._request(query, variables, level=level + 1)
                raise Failed(f"AniList Error: Connection Failed")
            else:
                raise Failed(f"AniList Error: {json_obj['errors'][0]['message']}")
        else:
            time.sleep(60 / 90)
        return json_obj

    def _validate_id(self, anilist_id):
        query = "query ($id: Int) {Media(id: $id) {id title{romaji english}}}"
        media = self._request(query, {"id": anilist_id})["data"]["Media"]
        if media["id"]:
            return media["id"], media["title"]["english" if media["title"]["english"] else "romaji"]
        raise Failed(f"AniList Error: No AniList ID found for {anilist_id}")

    def _pagenation(self, query, limit=0, variables=None):
        anilist_ids = []
        count = 0
        page_num = 0
        if variables is None:
            variables = {}
        next_page = True
        while next_page:
            page_num += 1
            variables["page"] = page_num
            json_obj = self._request(query, variables)
            next_page = json_obj["data"]["Page"]["pageInfo"]["hasNextPage"]
            for media in json_obj["data"]["Page"]["media"]:
                if media["id"]:
                    anilist_ids.append(media["id"])
                    count += 1
                    if 0 < limit == count:
                        break
            if 0 < limit == count:
                break
        return anilist_ids

    def _search(self, **kwargs):
        query_vars = "$page: Int, $sort: [MediaSort]"
        media_vars = "sort: $sort, type: ANIME"
        variables = {"sort": "SCORE_DESC" if kwargs['sort_by'] == "score" else "POPULARITY_DESC"}
        for key, value in kwargs.items():
            if key not in ["sort_by", "limit"]:
                if "." in key:
                    attr, mod = key.split(".")
                else:
                    attr = key
                    mod = ""
                ani_attr = attr_translation[attr] if attr in attr_translation else attr
                final = ani_attr if attr in no_mod_searches else f"{ani_attr}_{mod_translation[mod]}"
                if attr in ["start", "end"]:
                    value = int(util.validate_date(value, f"anilist_search {key}", return_as="%Y%m%d"))
                elif attr in ["season", "format", "status", "genre", "tag", "tag_category"]:
                    value = self.options[attr.replace("_", " ").title()][value.replace(" / ", "-").replace(" ", "-")]
                if mod == "gte":
                    value -= 1
                elif mod == "lte":
                    value += 1
                query_vars += f", ${final}: {search_types[ani_attr]}"
                media_vars += f", {final}: ${final}"
                variables[key] = value
        query = f"query ({query_vars}) {{Page(page: $page){{pageInfo {{hasNextPage}}media({media_vars}){{id}}}}}}"
        logger.debug(query)
        return self._pagenation(query, limit=kwargs["limit"], variables=variables)

    def _studio(self, studio_id):
        query = """
            query ($page: Int, $id: Int) {
              Studio(id: $id) {
                name
                media(page: $page) {
                  nodes {id type}
                  pageInfo {hasNextPage}
                }
              }
            }
        """
        anilist_ids = []
        page_num = 0
        next_page = True
        name = None
        while next_page:
            page_num += 1
            json_obj = self._request(query, {"id": studio_id, "page": page_num})
            if not name:
                name = json_obj["data"]["Studio"]["name"]
            next_page = json_obj["data"]["Studio"]["media"]["pageInfo"]["hasNextPage"]
            for media in json_obj["data"]["Studio"]["media"]["nodes"]:
                if media["id"] and media["type"] == "ANIME":
                    anilist_ids.append(media["id"])
        return anilist_ids, name

    def _relations(self, anilist_id, ignore_ids=None):
        query = """
            query ($id: Int) {
              Media(id: $id) {
                id
                relations {
                  edges {node{id type} relationType}
                  nodes {id type}
                }
              }
            }
        """
        new_anilist_ids = []
        anilist_ids = []
        name = ""
        if not ignore_ids:
            ignore_ids = [anilist_id]
            anilist_id, name = self._validate_id(anilist_id)
            anilist_ids.append(anilist_id)
        json_obj = self._request(query, {"id": anilist_id})
        edges = [media["node"]["id"] for media in json_obj["data"]["Media"]["relations"]["edges"]
                 if media["relationType"] not in ["CHARACTER", "OTHER"] and media["node"]["type"] == "ANIME"]
        for media in json_obj["data"]["Media"]["relations"]["nodes"]:
            if media["id"] and media["id"] not in ignore_ids and media["id"] in edges and media["type"] == "ANIME":
                new_anilist_ids.append(media["id"])
                ignore_ids.append(media["id"])
                anilist_ids.append(media["id"])

        for next_id in new_anilist_ids:
            new_relation_ids, ignore_ids, _ = self._relations(next_id, ignore_ids=ignore_ids)
            anilist_ids.extend(new_relation_ids)

        return anilist_ids, ignore_ids, name

    def validate(self, name, data):
        valid = []
        for d in util.get_list(data):
            data_check = d.lower().replace(" / ", "-").replace(" ", "-")
            if data_check in self.options[name]:
                valid.append(d)
        if len(valid) > 0:
            return valid
        raise Failed(f"AniList Error: {name}: {data} does not exist\nOptions: {', '.join([v for k, v in self.options[name].items()])}")

    def validate_anilist_ids(self, anilist_ids, studio=False):
        anilist_id_list = util.get_int_list(anilist_ids, "AniList ID")
        anilist_values = []
        query = f"query ($id: Int) {{{'Studio(id: $id) {name}' if studio else 'Media(id: $id) {id}'}}}"
        for anilist_id in anilist_id_list:
            try:
                self._request(query, {"id": anilist_id})
                anilist_values.append(anilist_id)
            except Failed as e:     logger.error(e)
        if len(anilist_values) > 0:
            return anilist_values
        raise Failed(f"AniList Error: No valid AniList IDs in {anilist_ids}")

    def get_anilist_ids(self, method, data):
        if method == "anilist_id":
            logger.info(f"Processing AniList ID: {data}")
            anilist_id, name = self._validate_id(data)
            anilist_ids = [anilist_id]
        elif method == "anilist_studio":
            anilist_ids, name = self._studio(data)
            logger.info(f"Processing AniList Studio: ({data}) {name} ({len(anilist_ids)} Anime)")
        elif method == "anilist_relations":
            anilist_ids, _, name = self._relations(data)
            logger.info(f"Processing AniList Relations: ({data}) {name} ({len(anilist_ids)} Anime)")
        else:
            if method == "anilist_popular":
                data = {"limit": data, "popularity.gt": 3, "sort_by": "popular"}
            elif method == "anilist_top_rated":
                data = {"limit": data, "score.gt": 3, "sort_by": "score"}
            elif method not in builders:
                raise Failed(f"AniList Error: Method {method} not supported")
            message = f"Processing {method.replace('_', ' ').title().replace('Anilist', 'AniList')}:\nSort By: {pretty_names[data['sort_by']]}"
            if data['limit'] > 0:
                message += f"\nLimit: {data['limit']}"
            for key, value in data.items():
                if "." in key:
                    attr, mod = key.split(".")
                else:
                    attr = key
                    mod = ""
                message += f"\n{attr.replace('_', ' ').title()} {util.mod_displays[mod]} {value}"
            util.print_multiline(message)
            anilist_ids = self._search(**data)
        logger.debug("")
        logger.debug(f"{len(anilist_ids)} AniList IDs Found: {anilist_ids}")
        return anilist_ids
