import json
import os
import random
import requests
import telebot
from telebot import types


# ---------------------------------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "توكن")
ADMIN_ID = int(os.getenv("ADMIN_ID", "6153895991"))
CHANNEL_USERNAME = "@editortrue"
DATA_FILE = "users_data.json"

DEFAULT_POSTER = "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=800"

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")


def safe_edit_or_send(chat_id, message_id, text, reply_markup=None):
    try:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=reply_markup, parse_mode="HTML")
    except Exception:
        try:
            bot.delete_message(chat_id, message_id)
        except Exception:
            pass
        bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode="HTML")


def send_media_with_fallback(chat_id, message_id_to_delete, photo_url, caption, reply_markup):
    """دالة مخصصة لإرسال الصور دائماً مع إمكانية حذف الرسالة السابقة وتوفير صورة بديلة"""
    try:
        if message_id_to_delete:
            try:
                bot.delete_message(chat_id, message_id_to_delete)
            except Exception:
                pass

        target_photo = photo_url if (photo_url and str(photo_url).startswith("http")) else DEFAULT_POSTER

        try:
            bot.send_photo(chat_id, photo=target_photo, caption=caption, reply_markup=reply_markup, parse_mode="HTML")
        except Exception as e:
            print(f"Failed to send primary photo ({target_photo}): {e}")
            bot.send_photo(chat_id, photo=DEFAULT_POSTER, caption=caption, reply_markup=reply_markup, parse_mode="HTML")
    except Exception as e:
        print(f"Media send error: {e}")
        bot.send_message(chat_id, caption, reply_markup=reply_markup, parse_mode="HTML")


# --- دالات التعامل مع ملف JSON للتخزين الحقيقي ---
def load_data() -> dict:
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading JSON file: {e}")
        return {}


def save_data(data: dict):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving JSON file: {e}")


def register_user(user_id: int, username: str = "", first_name: str = "") -> dict:
    data = load_data()
    uid = str(user_id)
    if uid not in data:
        data[uid] = {
            "username": username,
            "first_name": first_name or "مستخدم",
            "usage_count": 1,
            "rating": 0,
            "favorites": {"movies": {}, "series": {}}
        }
    else:
        data[uid]["usage_count"] = data[uid].get("usage_count", 0) + 1
        data[uid]["first_name"] = first_name or data[uid].get("first_name", "مستخدم")
        if username:
            data[uid]["username"] = username

    save_data(data)
    return data


def save_user_rating(user_id: int, rating: int):
    data = load_data()
    uid = str(user_id)
    if uid in data:
        data[uid]["rating"] = rating
        save_data(data)


def get_user_favs(user_id: int) -> dict:
    data = register_user(user_id)
    uid = str(user_id)
    return data[uid].get("favorites", {"movies": {}, "series": {}})


def save_user_favs(user_id: int, favs: dict):
    data = load_data()
    uid = str(user_id)
    if uid not in data:
        data[uid] = {"favorites": {"movies": {}, "series": {}}}
    data[uid]["favorites"] = favs
    save_data(data)


# --- دالة التحقق من الاشتراك الإجباري ---
def check_subscription(user_id: int) -> bool:
    if user_id == ADMIN_ID:
        return True
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ["creator", "administrator", "member"]
    except Exception as e:
        print(f"Sub check error: {e}")
        return True


def send_sub_required_message(chat_id):
    markup = types.InlineKeyboardMarkup(row_width=1)
    ch_clean = CHANNEL_USERNAME.replace("@", "")
    markup.add(
        types.InlineKeyboardButton("📢 اشترك في القناة الرسمية", url=f"https://t.me/{ch_clean}"),
        types.InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_sub")
    )
    text = (
        f"✨ <b>أهلاً بك عزيزي!</b>\n\n"
        f"⚠️ <b>يجب عليك الاشتراك في قناة البوت لاستخدام الخدمات:</b>\n"
        f"📢 القناة: {CHANNEL_USERNAME}\n\n"
        f"👇 اشترك الآن ثم اضغط على زر <b>'تحقق من الاشتراك'</b>."
    )
    bot.send_message(chat_id, text, reply_markup=markup)


def parse_genres(genres_data) -> str:
    if not genres_data:
        return ""
    if isinstance(genres_data, list):
        items = []
        for g in genres_data:
            if isinstance(g, dict):
                name = g.get("name") or g.get("title") or g.get("name_ar")
                if name:
                    items.append(str(name))
            elif isinstance(g, str):
                items.append(g)
            else:
                items.append(str(g))
        return ", ".join(items)
    elif isinstance(genres_data, str):
        return genres_data
    return ""


# ---------------------------------------------------------
# 2. كلاس التعامل مع API المصدر (OscarAPI)
# ---------------------------------------------------------
class OscarAPI:
    OSCAR_URL = "https://mode.giize.com/OscarTV.php"
    MOVIES_URL = "https://ostvapp.cam/api/movies/"
    MOVIE_DETAILS_URL = "https://ostvapp.cam/api/movies/show.php"
    SERIES_URL = "https://ostvapp.cam/api/series/"
    SERIES_DETAILS_URL = "https://ostvapp.cam/api/series/show.php"
    ANIME_URL = "https://ostvapp.cam/api/anime/"
    ANIME_DETAILS_URL = "https://ostvapp.cam/api/anime/show.php"
    ANIME_EPISODES_URL = "https://ostvapp.cam/api/anime/episodes/"
    EPISODES_URL = "https://ostvapp.cam/api/episodes/"
    EPISODE_DETAILS_URL = "https://ostvapp.cam/api/episodes/show.php"
    ANIME_EPISODE_DETAILS_URL = "https://ostvapp.cam/api/anime/episodes/show.php"
    WRESTLING_URL = "https://ostvapp.cam/api/wrestling/"
    WRESTLING_DETAILS_URL = "https://ostvapp.cam/api/wrestling/show.php"
    BASE_MEDIA_URL = "https://ostvapp.cam"

    def __init__(self, timeout: int = 25):
        self.timeout = timeout
        self.session = requests.Session()

    def get_headers(self, target_url: str):
        try:
            res = self.session.post(self.OSCAR_URL, data={"link": target_url}, timeout=self.timeout)
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, dict) and "headers" in data and isinstance(data["headers"], dict):
                    data = data["headers"]
                if isinstance(data, dict):
                    return {str(k): str(v) for k, v in data.items() if isinstance(v, (str, int, float))}
        except Exception as e:
            print(f"Error fetching headers for {target_url}: {e}")
        return None

    def get_movies(self, page: int = 1, limit: int = 20, sort_by: str = "most_viewed"):
        target_url = f"{self.MOVIES_URL}?page={page}&limit={limit}&sort_by={sort_by}&app_version=15"
        headers = self.get_headers(target_url)
        params = {"page": page, "limit": limit, "sort_by": sort_by, "app_version": 15}
        try:
            res = self.session.get(self.MOVIES_URL, headers=headers, params=params, timeout=self.timeout)
            return res.json() if res.status_code == 200 else None
        except Exception as e:
            print(f"Error fetching movies: {e}")
            return None

    def search_movies(self, query: str, page: int = 1, limit: int = 20):
        target_url = f"{self.MOVIES_URL}?page={page}&limit={limit}&search={query}&app_version=15"
        headers = self.get_headers(target_url)
        params = {"page": page, "limit": limit, "search": query, "app_version": 15}
        try:
            res = self.session.get(self.MOVIES_URL, headers=headers, params=params, timeout=self.timeout)
            return res.json() if res.status_code == 200 else None
        except Exception as e:
            print(f"Error searching movies: {e}")
            return None

    def get_movie_details(self, movie_id: int):
        target_url = f"{self.MOVIE_DETAILS_URL}?id={movie_id}"
        headers = self.get_headers(target_url)
        try:
            res = self.session.get(self.MOVIE_DETAILS_URL, headers=headers, params={"id": movie_id}, timeout=self.timeout)
            return res.json() if res.status_code == 200 else None
        except Exception as e:
            print(f"Error fetching movie details: {e}")
            return None

    def get_series(self, page: int = 1, limit: int = 20, sort_by: str = "most_viewed"):
        target_url = f"{self.SERIES_URL}?page={page}&limit={limit}&sort_by={sort_by}&app_version=15"
        headers = self.get_headers(target_url)
        params = {"page": page, "limit": limit, "sort_by": sort_by, "app_version": 15}
        try:
            res = self.session.get(self.SERIES_URL, headers=headers, params=params, timeout=self.timeout)
            return res.json() if res.status_code == 200 else None
        except Exception as e:
            print(f"Error fetching series: {e}")
            return None

    def search_series(self, query: str, page: int = 1, limit: int = 20):
        target_url = f"{self.SERIES_URL}?page={page}&limit={limit}&search={query}&app_version=15"
        headers = self.get_headers(target_url)
        params = {"page": page, "limit": limit, "search": query, "app_version": 15}
        try:
            res = self.session.get(self.SERIES_URL, headers=headers, params=params, timeout=self.timeout)
            return res.json() if res.status_code == 200 else None
        except Exception as e:
            print(f"Error searching series: {e}")
            return None

    def get_series_details(self, series_id: int):
        target_url = f"{self.SERIES_DETAILS_URL}?id={series_id}"
        headers = self.get_headers(target_url)
        try:
            res = self.session.get(self.SERIES_DETAILS_URL, headers=headers, params={"id": series_id}, timeout=self.timeout)
            return res.json() if res.status_code == 200 else None
        except Exception as e:
            print(f"Error fetching series details: {e}")
            return None

    def get_anime_movies(self, page: int = 1, limit: int = 20):
        target_url = f"{self.ANIME_URL}?page={page}&limit={limit}&anime_type=movie"
        headers = self.get_headers(target_url)
        params = {"page": page, "limit": limit, "anime_type": "movie"}
        try:
            res = self.session.get(self.ANIME_URL, headers=headers, params=params, timeout=self.timeout)
            return res.json() if res.status_code == 200 else None
        except Exception as e:
            print(f"Error fetching anime movies: {e}")
            return None

    def get_anime_series(self, page: int = 1, limit: int = 20):
        target_url = f"{self.ANIME_URL}?page={page}&limit={limit}&anime_type=tv,ova,ona,special&sort_by=latest_episode"
        headers = self.get_headers(target_url)
        params = {"page": page, "limit": limit, "anime_type": "tv,ova,ona,special", "sort_by": "latest_episode"}
        try:
            res = self.session.get(self.ANIME_URL, headers=headers, params=params, timeout=self.timeout)
            return res.json() if res.status_code == 200 else None
        except Exception as e:
            print(f"Error fetching anime series: {e}")
            return None

    def get_anime_details(self, anime_id: int):
        target_url = f"{self.ANIME_DETAILS_URL}?id={anime_id}"
        headers = self.get_headers(target_url)
        try:
            res = self.session.get(self.ANIME_DETAILS_URL, headers=headers, params={"id": anime_id}, timeout=self.timeout)
            return res.json() if res.status_code == 200 else None
        except Exception as e:
            print(f"Error fetching anime details: {e}")
            return None

    def get_anime_episodes(self, anime_id: int, page: int = 1, per_page: int = 20, season_id: int = None):
        target_url = f"{self.ANIME_EPISODES_URL}?anime_id={anime_id}&page={page}&per_page={per_page}"
        if season_id:
            target_url += f"&season_id={season_id}"
        
        headers = self.get_headers(target_url)
        params = {"anime_id": anime_id, "page": page, "per_page": per_page}
        if season_id:
            params["season_id"] = season_id
            
        try:
            res = self.session.get(self.ANIME_EPISODES_URL, headers=headers, params=params, timeout=self.timeout)
            return res.json() if res.status_code == 200 else None
        except Exception as e:
            print(f"Error fetching anime episodes: {e}")
            return None

    def get_season_episodes(self, season_id: int, page: int = 1, per_page: int = 20, sort: str = "asc"):
        target_url = f"{self.EPISODES_URL}?season_id={season_id}&page={page}&per_page={per_page}&sort={sort}"
        headers = self.get_headers(target_url)
        params = {"season_id": season_id, "page": page, "per_page": per_page, "sort": sort}
        try:
            res = self.session.get(self.EPISODES_URL, headers=headers, params=params, timeout=self.timeout)
            return res.json() if res.status_code == 200 else None
        except Exception as e:
            print(f"Error fetching season episodes: {e}")
            return None

    def get_episode_details(self, episode_id: int):
        target_url = f"{self.EPISODE_DETAILS_URL}?id={episode_id}"
        headers = self.get_headers(target_url)
        try:
            res = self.session.get(self.EPISODE_DETAILS_URL, headers=headers, params={"id": episode_id}, timeout=self.timeout)
            return res.json() if res.status_code == 200 else None
        except Exception as e:
            print(f"Error fetching episode details: {e}")
            return None

    def get_anime_episode_details(self, episode_id: int):
        target_url = f"{self.ANIME_EPISODE_DETAILS_URL}?id={episode_id}"
        headers = self.get_headers(target_url)
        try:
            res = self.session.get(self.ANIME_EPISODE_DETAILS_URL, headers=headers, params={"id": episode_id}, timeout=self.timeout)
            return res.json() if res.status_code == 200 else None
        except Exception as e:
            print(f"Error fetching anime episode details: {e}")
            return None

    def get_wrestling(self, page: int = 1, limit: int = 20):
        target_url = f"{self.WRESTLING_URL}?page={page}&limit={limit}"
        headers = self.get_headers(target_url)
        params = {"page": page, "limit": limit}
        try:
            res = self.session.get(self.WRESTLING_URL, headers=headers, params=params, timeout=self.timeout)
            return res.json() if res.status_code == 200 else None
        except Exception as e:
            print(f"Error fetching wrestling: {e}")
            return None

    def get_wrestling_details(self, wrestling_id: int):
        target_url = f"{self.WRESTLING_DETAILS_URL}?id={wrestling_id}"
        headers = self.get_headers(target_url)
        try:
            res = self.session.get(self.WRESTLING_DETAILS_URL, headers=headers, params={"id": wrestling_id}, timeout=self.timeout)
            return res.json() if res.status_code == 200 else None
        except Exception as e:
            print(f"Error fetching wrestling details: {e}")
            return None


api = OscarAPI()


# ---------------------------------------------------------
# 3. لوحات التحكم (Keyboards)
# ---------------------------------------------------------
def get_main_keyboard(is_admin: bool = False):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🎬 الأفلام", callback_data="mpage_1_most_viewed"),
        types.InlineKeyboardButton("📺 المسلسلات", callback_data="spage_1_most_viewed"),
        types.InlineKeyboardButton("⛩️ أفلام أنمي", callback_data="ampage_1"),
        types.InlineKeyboardButton("🌸 مسلسلات أنمي", callback_data="aspage_1"),
        types.InlineKeyboardButton("🤼‍♂️ المصارعة الحرة", callback_data="wpage_1"),
        types.InlineKeyboardButton("🔍 بحث شامل", callback_data="src_prompt"),
        types.InlineKeyboardButton("❤️ المفضلة", callback_data="show_favs"),
        types.InlineKeyboardButton("🔥 ترند الأكثر استخداماً", callback_data="show_top_users"),
        types.InlineKeyboardButton("🎲 اقتراح عشوائي", callback_data="random_recommend"),
        types.InlineKeyboardButton("⭐ تقييم البوت", callback_data="rate_bot_menu")
    )
    if is_admin:
        markup.add(types.InlineKeyboardButton("⚙️ لوحة الأدمن الخاصة", callback_data="admin_panel_open"))
    return markup


def build_movies_keyboard(movies: list, page: int, sort_by: str = "most_viewed", is_anime: bool = False):
    markup = types.InlineKeyboardMarkup(row_width=1)
    if not is_anime:
        other_sort = "latest" if sort_by == "most_viewed" else "most_viewed"
        other_label = "🔄 التبديل إلى الأحدث" if sort_by == "most_viewed" else "🔄 التبديل للأكثر مشاهدة"
        markup.add(types.InlineKeyboardButton(other_label, callback_data=f"mpage_1_{other_sort}"))

    for m in movies:
        title = m.get("title_ar") or m.get("title_en", "فيلم")
        year = m.get("release_year", "")
        cb = f"adet_{m['id']}" if is_anime else f"mdet_{m['id']}"
        markup.add(types.InlineKeyboardButton(f"📽️ {title} ({year})", callback_data=cb))

    nav = []
    prefix = "ampage_" if is_anime else "mpage_"
    jump_tag = "jump_am" if is_anime else f"jump_m_{sort_by}"

    if page > 1:
        cb_prev = f"{prefix}{page - 1}" if is_anime else f"{prefix}{page - 1}_{sort_by}"
        nav.append(types.InlineKeyboardButton("⬅️ السابق", callback_data=cb_prev))

    nav.append(types.InlineKeyboardButton(f"🔢 صفحة {page}", callback_data=jump_tag))

    if len(movies) > 0:
        cb_next = f"{prefix}{page + 1}" if is_anime else f"{prefix}{page + 1}_{sort_by}"
        nav.append(types.InlineKeyboardButton("التالي ➡️", callback_data=cb_next))

    markup.row(*nav)
    markup.add(types.InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu"))
    return markup


def build_series_keyboard(series_list: list, page: int, sort_by: str = "most_viewed", is_anime: bool = False):
    markup = types.InlineKeyboardMarkup(row_width=1)
    if not is_anime:
        other_sort = "latest" if sort_by == "most_viewed" else "most_viewed"
        other_label = "🔄 التبديل إلى الأحدث" if sort_by == "most_viewed" else "🔄 التبديل للأكثر مشاهدة"
        markup.add(types.InlineKeyboardButton(other_label, callback_data=f"spage_1_{other_sort}"))

    for s in series_list:
        title = s.get("title_ar") or s.get("title_en", "مسلسل")
        year = s.get("release_year", "")
        cb = f"adet_{s['id']}" if is_anime else f"sdet_{s['id']}"
        markup.add(types.InlineKeyboardButton(f"📺 {title} ({year})", callback_data=cb))

    nav = []
    prefix = "aspage_" if is_anime else "spage_"
    jump_tag = "jump_as" if is_anime else f"jump_s_{sort_by}"

    if page > 1:
        cb_prev = f"{prefix}{page - 1}" if is_anime else f"{prefix}{page - 1}_{sort_by}"
        nav.append(types.InlineKeyboardButton("⬅️ السابق", callback_data=cb_prev))

    nav.append(types.InlineKeyboardButton(f"🔢 صفحة {page}", callback_data=jump_tag))

    if len(series_list) > 0:
        cb_next = f"{prefix}{page + 1}" if is_anime else f"{prefix}{page + 1}_{sort_by}"
        nav.append(types.InlineKeyboardButton("التالي ➡️", callback_data=cb_next))

    markup.row(*nav)
    markup.add(types.InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu"))
    return markup


def build_wrestling_keyboard(wrestling_list: list, page: int):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for w in wrestling_list:
        title = w.get("title_ar") or w.get("title_en", "عرض مصارعة")
        date_str = w.get("air_date", "")
        markup.add(types.InlineKeyboardButton(f"🤼‍♂️ {title} ({date_str})", callback_data=f"wdet_{w['id']}"))

    nav = []
    if page > 1:
        nav.append(types.InlineKeyboardButton("⬅️ السابق", callback_data=f"wpage_{page - 1}"))

    nav.append(types.InlineKeyboardButton(f"🔢 صفحة {page}", callback_data="jump_w"))

    if len(wrestling_list) > 0:
        nav.append(types.InlineKeyboardButton("التالي ➡️", callback_data=f"wpage_{page + 1}"))

    markup.row(*nav)
    markup.add(types.InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu"))
    return markup


def build_series_details_keyboard(series_data: dict, user_id: int, is_anime: bool = False):
    markup = types.InlineKeyboardMarkup(row_width=2)
    seasons = series_data.get("seasons", [])
    s_id = series_data.get("id")

    # إصلاح مواسم الأنمي وتجاوبها بشكل دقيق
    if is_anime:
        valid_seasons = [s for s in seasons if isinstance(s, dict) and s.get("id")] if isinstance(seasons, list) else []
        if valid_seasons:
            for s in valid_seasons:
                s_num = s.get("season_number", 1)
                count = s.get("episodes_count", 0)
                season_id = s.get("id")
                markup.add(types.InlineKeyboardButton(f"📁 الموسم {s_num} ({count} حلقة)", callback_data=f"asn_{s_id}_{season_id}_1"))
        else:
            ep_count = series_data.get("episode_count") or series_data.get("episodes_count") or 0
            count_str = f" ({ep_count} حلقة)" if ep_count else ""
            markup.add(types.InlineKeyboardButton(f"📺 عرض جميع الحلقات{count_str}", callback_data=f"asn_{s_id}_0_1"))
    elif seasons:
        for s in seasons:
            s_num = s.get("season_number", 1)
            count = s.get("episodes_count", 0)
            markup.add(types.InlineKeyboardButton(f"📁 الموسم {s_num} ({count} حلقة)", callback_data=f"sn_{s['id']}_1"))

    favs = get_user_favs(user_id)["series"]
    if str(s_id) in favs or s_id in favs:
        markup.add(types.InlineKeyboardButton("💔 إزالة من المفضلة", callback_data=f"tfav_s_{s_id}"))
    else:
        markup.add(types.InlineKeyboardButton("❤️ إضافة للمفضلة", callback_data=f"tfav_s_{s_id}"))

    markup.add(types.InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu"))
    return markup


def build_episodes_keyboard(episodes: list, parent_id: int, page: int, is_anime: bool = False, season_id: int = 0):
    markup = types.InlineKeyboardMarkup(row_width=4)
    prefix_ep = "aep_" if is_anime else "ep_"

    ep_buttons = [types.InlineKeyboardButton(f"حـ {ep.get('episode_number', '?')}", callback_data=f"{prefix_ep}{ep['id']}") for ep in episodes]
    markup.add(*ep_buttons)

    nav = []
    if is_anime:
        cb_base = f"asn_{parent_id}_{season_id}_"
    else:
        cb_base = f"sn_{parent_id}_"

    if page > 1:
        nav.append(types.InlineKeyboardButton("⬅️", callback_data=f"{cb_base}{page - 1}"))
    nav.append(types.InlineKeyboardButton(f"صفحة {page}", callback_data="noop"))
    if len(episodes) > 0:
        nav.append(types.InlineKeyboardButton("➡️", callback_data=f"{cb_base}{page + 1}"))

    markup.row(*nav)
    markup.add(types.InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu"))
    return markup


def build_links_keyboard(watch_links: list, download_links: list, item_id: int = None, is_movie: bool = True, user_id: int = None):
    markup = types.InlineKeyboardMarkup(row_width=1)

    if watch_links:
        for link in watch_links:
            server, quality, url = link.get("server_name", "سيرفر"), link.get("quality", ""), link.get("url")
            if url:
                markup.add(types.InlineKeyboardButton(f"▶️ مشاهدة ({quality} - {server})", url=url))

    if download_links:
        for link in download_links:
            quality, size, url = link.get("quality", ""), link.get("file_size", ""), link.get("url")
            if url:
                markup.add(types.InlineKeyboardButton(f"📥 تحميل ({quality} - {size})", url=url))

    if is_movie and item_id and user_id:
        favs = get_user_favs(user_id)["movies"]
        if str(item_id) in favs or item_id in favs:
            markup.add(types.InlineKeyboardButton("💔 إزالة من المفضلة", callback_data=f"tfav_m_{item_id}"))
        else:
            markup.add(types.InlineKeyboardButton("❤️ إضافة للمفضلة", callback_data=f"tfav_m_{item_id}"))

    markup.add(types.InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu"))
    return markup


# ---------------------------------------------------------
# 4. لوحة تحكم الأدمن والإذاعة
# ---------------------------------------------------------
@bot.message_handler(commands=["admin", "bc", "broadcast", "stats"])
def admin_panel_handler(message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID:
        return

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📢 إذاعة للمستخدمين", callback_data="start_bc"),
        types.InlineKeyboardButton("📊 الإحصائيات الشاملة", callback_data="admin_stats")
    )
    bot.send_message(message.chat.id, "⚙️ <b>لوحة تحكم الأدمن:</b>", reply_markup=markup)


def start_broadcast_step(message):
    if message.from_user.id != ADMIN_ID:
        return

    data = load_data()
    users = list(data.keys())

    if not users:
        bot.send_message(message.chat.id, "❌ لا يوجد مستخدمين لإرسال الإذاعة إليهم.")
        return

    status_msg = bot.send_message(message.chat.id, f"⏳ <b>جاري بدء الإذاعة لـ {len(users)} مستخدم...</b>")
    success, failed = 0, 0

    for uid in users:
        try:
            bot.copy_message(chat_id=int(uid), from_chat_id=message.chat.id, message_id=message.message_id)
            success += 1
        except Exception:
            failed += 1

    bot.edit_message_text(
        f"✅ <b>تم الانتهاء من الإذاعة بنجاح!</b>\n\n"
        f"🟢 نجح الإرسال: <b>{success}</b>\n"
        f"🔴 فشل الإرسال (حظر/حساب محذوف): <b>{failed}</b>\n"
        f"👥 الإجمالي: <b>{len(users)}</b>",
        chat_id=message.chat.id,
        message_id=status_msg.message_id
    )


# ---------------------------------------------------------
# 5. معالجة الانتقال المباشر برقم الصفحة
# ---------------------------------------------------------
def process_jump_m(message, sort_by):
    chat_id = message.chat.id
    if not message.text or not message.text.isdigit():
        bot.send_message(chat_id, "❌ <b>رجاءً أدخل رقم صفحة صحيح (أرقام فقط).</b>", reply_markup=get_main_keyboard(chat_id == ADMIN_ID))
        return

    page = max(1, int(message.text))
    bot.send_message(chat_id, f"⏳ <b>جاري جلب الصفحة {page} للأفلام...</b>")
    res = api.get_movies(page=page, limit=20, sort_by=sort_by)

    if res and res.get("status") == "success":
        movies = res.get("data", [])
        if not movies:
            bot.send_message(chat_id, f"⚠️ <b>لا توجد أفلام في الصفحة {page}.</b>", reply_markup=get_main_keyboard(chat_id == ADMIN_ID))
            return

        keyboard = build_movies_keyboard(movies, page, sort_by)
        sort_title = "الأكثر مشاهدة 🔥" if sort_by == "most_viewed" else "الأحدث 🆕"
        bot.send_message(chat_id, f"🎬 <b>قائمة الأفلام ({sort_title}) - صفحة {page}:</b>", reply_markup=keyboard)
    else:
        bot.send_message(chat_id, "❌ <b>حدث خطأ أثناء جلب البيانات.</b>", reply_markup=get_main_keyboard(chat_id == ADMIN_ID))


def process_jump_s(message, sort_by):
    chat_id = message.chat.id
    if not message.text or not message.text.isdigit():
        bot.send_message(chat_id, "❌ <b>رجاءً أدخل رقم صفحة صحيح (أرقام فقط).</b>", reply_markup=get_main_keyboard(chat_id == ADMIN_ID))
        return

    page = max(1, int(message.text))
    bot.send_message(chat_id, f"⏳ <b>جاري جلب الصفحة {page} للمسلسلات...</b>")
    res = api.get_series(page=page, limit=20, sort_by=sort_by)

    if res and res.get("status") == "success":
        series_list = res.get("data", [])
        if not series_list:
            bot.send_message(chat_id, f"⚠️ <b>لا توجد مسلسلات في الصفحة {page}.</b>", reply_markup=get_main_keyboard(chat_id == ADMIN_ID))
            return

        keyboard = build_series_keyboard(series_list, page, sort_by)
        sort_title = "الأكثر مشاهدة 🔥" if sort_by == "most_viewed" else "الأحدث 🆕"
        bot.send_message(chat_id, f"📺 <b>قائمة المسلسلات ({sort_title}) - صفحة {page}:</b>", reply_markup=keyboard)
    else:
        bot.send_message(chat_id, "❌ <b>حدث خطأ أثناء جلب البيانات.</b>", reply_markup=get_main_keyboard(chat_id == ADMIN_ID))


def process_jump_am(message):
    chat_id = message.chat.id
    if not message.text or not message.text.isdigit():
        bot.send_message(chat_id, "❌ <b>رجاءً أدخل رقم صفحة صحيح.</b>", reply_markup=get_main_keyboard(chat_id == ADMIN_ID))
        return
    page = max(1, int(message.text))
    bot.send_message(chat_id, f"⏳ <b>جاري جلب الصفحة {page} لأفلام الأنمي...</b>")
    res = api.get_anime_movies(page=page, limit=20)
    if res and res.get("status") == "success":
        movies = res.get("data", [])
        if not movies:
            bot.send_message(chat_id, f"⚠️ <b>لا توجد أفلام أنمي في الصفحة {page}.</b>", reply_markup=get_main_keyboard(chat_id == ADMIN_ID))
            return
        keyboard = build_movies_keyboard(movies, page, is_anime=True)
        bot.send_message(chat_id, f"⛩️ <b>قائمة أفلام الأنمي - صفحة {page}:</b>", reply_markup=keyboard)


def process_jump_as(message):
    chat_id = message.chat.id
    if not message.text or not message.text.isdigit():
        bot.send_message(chat_id, "❌ <b>رجاءً أدخل رقم صفحة صحيح.</b>", reply_markup=get_main_keyboard(chat_id == ADMIN_ID))
        return
    page = max(1, int(message.text))
    bot.send_message(chat_id, f"⏳ <b>جاري جلب الصفحة {page} لمسلسلات الأنمي...</b>")
    res = api.get_anime_series(page=page, limit=20)
    if res and res.get("status") == "success":
        series_list = res.get("data", [])
        if not series_list:
            bot.send_message(chat_id, f"⚠️ <b>لا توجد مسلسلات أنمي في الصفحة {page}.</b>", reply_markup=get_main_keyboard(chat_id == ADMIN_ID))
            return
        keyboard = build_series_keyboard(series_list, page, is_anime=True)
        bot.send_message(chat_id, f"🌸 <b>قائمة مسلسلات الأنمي - صفحة {page}:</b>", reply_markup=keyboard)


def process_jump_w(message):
    chat_id = message.chat.id
    if not message.text or not message.text.isdigit():
        bot.send_message(chat_id, "❌ <b>رجاءً أدخل رقم صفحة صحيح.</b>", reply_markup=get_main_keyboard(chat_id == ADMIN_ID))
        return
    page = max(1, int(message.text))
    bot.send_message(chat_id, f"⏳ <b>جاري جلب الصفحة {page} لعروض المصارعة...</b>")
    res = api.get_wrestling(page=page, limit=20)
    if res and res.get("status") == "success":
        wrestling_list = res.get("data", [])
        if not wrestling_list:
            bot.send_message(chat_id, f"⚠️ <b>لا توجد عروض مصارعة في الصفحة {page}.</b>", reply_markup=get_main_keyboard(chat_id == ADMIN_ID))
            return
        keyboard = build_wrestling_keyboard(wrestling_list, page)
        bot.send_message(chat_id, f"🤼‍♂️ <b>قائمة عروض المصارعة - صفحة {page}:</b>", reply_markup=keyboard)


# ---------------------------------------------------------
# 6. معالجة الأوامر والبحث
# ---------------------------------------------------------
@bot.message_handler(commands=["start"])
def send_welcome(message):
    user = message.from_user
    register_user(user.id, user.username or "", user.first_name or "")

    if not check_subscription(user.id):
        send_sub_required_message(message.chat.id)
        return

    is_admin = (user.id == ADMIN_ID)
    bot.send_message(
        message.chat.id,
        f"<b>✨ أهلاً بك يا {user.first_name} في بوت سينما Oscar TV الفاخر! 🔥</b>\n\n"
        f"🎬 اختر ما تريد من القائمة بالأسفل، أو استخدم البحث المباشر للوصول لأفضل الأفلام، المسلسلات، الأنمي، وعروض المصارعة 🍿:",
        reply_markup=get_main_keyboard(is_admin),
    )


@bot.message_handler(commands=["search"])
def search_command(message):
    user = message.from_user
    register_user(user.id, user.username or "", user.first_name or "")

    if not check_subscription(user.id):
        send_sub_required_message(message.chat.id)
        return

    msg = bot.send_message(message.chat.id, "🔍 <b>أدخل اسم الفيلم أو المسلسل للبحث:</b>")
    bot.register_next_step_handler(msg, process_search)


def process_search(message):
    query = message.text.strip() if message.text else ""
    if not query:
        bot.send_message(message.chat.id, "❌ إدخال غير صالح.", reply_markup=get_main_keyboard(message.from_user.id == ADMIN_ID))
        return

    bot.send_message(message.chat.id, "⏳ <b>جاري البحث في قاعدة البيانات...</b>")

    s_res = api.search_series(query=query, page=1, limit=10)
    m_res = api.search_movies(query=query, page=1, limit=10)

    series_list = s_res.get("data", []) if s_res and s_res.get("status") == "success" else []
    movies_list = m_res.get("data", []) if m_res and m_res.get("status") == "success" else []

    if not series_list and not movies_list:
        bot.send_message(
            message.chat.id,
            f"❌ لم يتم العثور على أي نتائج لـ: <b>{query}</b>",
            reply_markup=get_main_keyboard(message.from_user.id == ADMIN_ID),
        )
        return

    markup = types.InlineKeyboardMarkup(row_width=1)

    if series_list:
        markup.add(types.InlineKeyboardButton("─── 📺 نتائج المسلسلات ───", callback_data="noop"))
        for s in series_list:
            title = s.get("title_ar") or s.get("title_en", "مسلسل")
            year = s.get("release_year", "")
            ep_count = s.get("episode_count")
            ep_str = f" | {ep_count} حلقة" if ep_count else ""
            markup.add(types.InlineKeyboardButton(f"📺 {title} ({year}){ep_str}", callback_data=f"sdet_{s['id']}"))

    if movies_list:
        markup.add(types.InlineKeyboardButton("─── 🎬 نتائج الأفلام ───", callback_data="noop"))
        for m in movies_list:
            title = m.get("title_ar") or m.get("title_en", "فيلم")
            year = m.get("release_year", "")
            markup.add(types.InlineKeyboardButton(f"📽️ {title} ({year})", callback_data=f"mdet_{m['id']}"))

    markup.add(types.InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu"))
    bot.send_message(message.chat.id, f"🔍 <b>نتائج البحث عن ({query}):</b>", reply_markup=markup)


# ---------------------------------------------------------
# 7. معالجة الأحداث والأزرار (Callbacks)
# ---------------------------------------------------------
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    user = call.from_user
    user_id = user.id
    data = call.data

    register_user(user_id, user.username or "", user.first_name or "")

    if data == "check_sub":
        if check_subscription(user_id):
            bot.answer_callback_query(call.id, "✅ شكراً لااشتراكك! يمكنك استخدام البوت الآن.")
            bot.send_message(chat_id, "<b>🎬 أهلاً بك في بوت سينما Oscar TV المطور!</b>", reply_markup=get_main_keyboard(user_id == ADMIN_ID))
        else:
            bot.answer_callback_query(call.id, "❌ لم تشترك بعد! اشترك بالقناة ثم حاول مجدداً.", show_alert=True)
        return

    if not check_subscription(user_id):
        bot.answer_callback_query(call.id, "⚠️ يجب الاشتراك في القناة أولاً!", show_alert=True)
        send_sub_required_message(chat_id)
        return

    if data == "noop":
        bot.answer_callback_query(call.id)
        return

    # --- عروض المصارعة الحرة ---
    elif data.startswith("wpage_"):
        page = int(data.split("_")[1])
        bot.answer_callback_query(call.id, "جاري تحميل عروض المصارعة...")
        res = api.get_wrestling(page=page, limit=20)
        if res and res.get("status") == "success":
            wrestling_list = res.get("data", [])
            if not wrestling_list and page > 1:
                bot.answer_callback_query(call.id, "⚠️ وصلت لنهاية القائمة.", show_alert=True)
                return
            keyboard = build_wrestling_keyboard(wrestling_list, page)
            safe_edit_or_send(chat_id, call.message.message_id, f"🤼‍♂️ <b>قائمة عروض المصارعة - صفحة {page}:</b>", keyboard)

    elif data.startswith("wdet_"):
        w_id = int(data.split("_")[1])
        bot.answer_callback_query(call.id, "جاري تحميل تفاصيل عرض المصارعة...")
        res = api.get_wrestling_details(w_id)

        if res and res.get("status") == "success":
            w = res["data"]
            title = w.get("title_ar") or w.get("title_en", "")
            air_date = w.get("air_date", "N/A")
            cat_name = w.get("category", {}).get("name", "غير محدد") if w.get("category") else "غير محدد"
            desc = w.get("description") or "لا يوجد وصف إضافي."

            caption = f"🤼‍♂️ <b>{title}</b>\n📅 تاريخ العرض: <b>{air_date}</b>\n🏷️ الفئة: <b>{cat_name}</b>\n\n📝 <b>الوصف:</b>\n<i>{desc[:400]}</i>"

            poster = w.get("poster")
            poster_url = f"{api.BASE_MEDIA_URL}{poster}" if poster else None
            keyboard = build_links_keyboard(w.get("watch_links", []), w.get("download_links", []), is_movie=False)

            send_media_with_fallback(chat_id, call.message.message_id, poster_url, caption, keyboard)

    elif data == "jump_w":
        bot.answer_callback_query(call.id)
        msg = bot.send_message(chat_id, "🔢 <b>أدخل رقم صفحة المصارعة التي تريد الانتقال إليها:</b>")
        bot.register_next_step_handler(msg, process_jump_w)

    # --- أفلام أنمي ---
    elif data.startswith("ampage_"):
        page = int(data.split("_")[1])
        bot.answer_callback_query(call.id, "جاري تحميل أفلام الأنمي...")
        res = api.get_anime_movies(page=page, limit=20)
        if res and res.get("status") == "success":
            movies = res.get("data", [])
            if not movies and page > 1:
                bot.answer_callback_query(call.id, "⚠️ وصلت لنهاية الأفلام.", show_alert=True)
                return
            keyboard = build_movies_keyboard(movies, page, is_anime=True)
            safe_edit_or_send(chat_id, call.message.message_id, f"⛩️ <b>قائمة أفلام الأنمي - صفحة {page}:</b>", keyboard)

    # --- مسلسلات أنمي ---
    elif data.startswith("aspage_"):
        page = int(data.split("_")[1])
        bot.answer_callback_query(call.id, "جاري تحميل مسلسلات الأنمي...")
        res = api.get_anime_series(page=page, limit=20)
        if res and res.get("status") == "success":
            series_list = res.get("data", [])
            if not series_list and page > 1:
                bot.answer_callback_query(call.id, "⚠️ وصلت لنهاية المسلسلات.", show_alert=True)
                return
            keyboard = build_series_keyboard(series_list, page, is_anime=True)
            safe_edit_or_send(chat_id, call.message.message_id, f"🌸 <b>قائمة مسلسلات الأنمي - صفحة {page}:</b>", keyboard)

    # --- تفاصيل الأنمي (فيلم / مسلسل) ---
    elif data.startswith("adet_"):
        a_id = int(data.split("_")[1])
        bot.answer_callback_query(call.id, "جاري تحميل تفاصيل الأنمي...")
        res = api.get_anime_details(a_id)

        if res and res.get("status") == "success":
            a = res["data"]
            title = a.get("title_ar") or a.get("title_en", "")
            year = a.get("release_year", "N/A")
            rating = a.get("rating", "N/A")
            story = a.get("story") or "لا توجد قصة متاحة."
            anime_type = a.get("anime_type", "tv")
            genres = parse_genres(a.get("genres") or a.get("genre_list"))
            genres_str = f"\n🏷️ التصنيف: {genres}" if genres else ""

            caption = f"🌸 <b>{title}</b> ({year})\n⭐ التقييم: {rating}{genres_str}\n\n📝 <b>القصة:</b>\n<i>{story[:500]}</i>"
            poster = a.get("poster")
            poster_url = f"{api.BASE_MEDIA_URL}{poster}" if poster else None

            if anime_type == "movie" or (a.get("watch_links") and not a.get("episodes_count")):
                keyboard = build_links_keyboard(a.get("watch_links", []), a.get("download_links", []), item_id=a_id, is_movie=True, user_id=user_id)
            else:
                keyboard = build_series_details_keyboard(a, user_id, is_anime=True)

            send_media_with_fallback(chat_id, call.message.message_id, poster_url, caption, keyboard)

    # --- جلب حلقات الأنمي (معالجة إصلاح زر الموسم والمواسم المتعددة) ---
    elif data.startswith("asn_"):
        parts = data.split("_")
        anime_id = int(parts[1])
        
        # التنسيق الجديد: asn_{anime_id}_{season_id}_{page}
        if len(parts) >= 4:
            season_id = int(parts[2])
            page = int(parts[3])
        elif len(parts) == 3:
            season_id = 0
            page = int(parts[2])
        else:
            season_id = 0
            page = 1

        bot.answer_callback_query(call.id, "جاري تحميل حلقات الأنمي...")
        
        # طلب الحلقات مع إرسال season_id إن وجد
        res = api.get_anime_episodes(anime_id=anime_id, page=page, per_page=20, season_id=season_id if season_id > 0 else None)

        if res and res.get("status") == "success":
            episodes = res.get("data", [])
            if not episodes and page > 1:
                bot.answer_callback_query(call.id, "⚠️ لا توجد حلقات أخرى.", show_alert=True)
                return
            elif not episodes:
                bot.answer_callback_query(call.id, "⚠️ لم يتم العثور على حلقات لهذا الموسم.", show_alert=True)
                return

            keyboard = build_episodes_keyboard(episodes, parent_id=anime_id, page=page, is_anime=True, season_id=season_id)
            safe_edit_or_send(chat_id, call.message.message_id, f"🌸 <b>حلقات الأنمي - صفحة {page}:</b>", keyboard)

    # --- تفاصيل حلقة الأنمي ---
    elif data.startswith("aep_"):
        ep_id = int(data.split("_")[1])
        bot.answer_callback_query(call.id, "جاري تحميل روابط الحلقة...")
        res = api.get_anime_episode_details(ep_id)

        if res and res.get("status") == "success":
            ep = res["data"]
            anime_title = ep.get("anime_title") or ep.get("anime_title_en", "أنمي")
            ep_num = ep.get("episode_number", "?")
            caption = f"📺 <b>{anime_title}</b> - الحلقة <b>{ep_num}</b>"

            thumb = ep.get("thumbnail") or ep.get("anime_poster")
            thumb_url = f"{api.BASE_MEDIA_URL}{thumb}" if thumb and str(thumb).startswith("/") else thumb

            keyboard = build_links_keyboard(ep.get("watch_links", []), ep.get("download_links", []), is_movie=False)
            send_media_with_fallback(chat_id, call.message.message_id, thumb_url, caption, keyboard)

    # --- الانتقال لرقم صفحة أنمي ---
    elif data == "jump_am":
        bot.answer_callback_query(call.id)
        msg = bot.send_message(chat_id, "🔢 <b>أدخل رقم صفحة أفلام الأنمي التي تريد الانتقال إليها:</b>")
        bot.register_next_step_handler(msg, process_jump_am)

    elif data == "jump_as":
        bot.answer_callback_query(call.id)
        msg = bot.send_message(chat_id, "🔢 <b>أدخل رقم صفحة مسلسلات الأنمي التي تريد الانتقال إليها:</b>")
        bot.register_next_step_handler(msg, process_jump_as)

    # --- ترند الأكثر استخداماً ---
    elif data == "show_top_users":
        bot.answer_callback_query(call.id)
        all_data = load_data()
        sorted_users = sorted(all_data.items(), key=lambda x: x[1].get("usage_count", 0), reverse=True)[:10]
        top_text = "🔥 <b>قائمة أساطير الترند (أكثر 10 استخداماً للبوت):</b>\n\n"
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

        for idx, (u_id, u_info) in enumerate(sorted_users):
            name = u_info.get("first_name", "مستخدم")
            count = u_info.get("usage_count", 0)
            medal = medals[idx] if idx < len(medals) else "👤"
            top_text += f"{medal} <b>{name}</b> — <code>{count}</code> تفاعل 🚀\n"

        top_text += "\n🌟 <i>استخدم البوت أكثر لتصبح في قمة القائمة!</i>"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu"))
        safe_edit_or_send(chat_id, call.message.message_id, top_text, markup)

    # --- اقتراح عشوائي ---
    elif data == "random_recommend":
        bot.answer_callback_query(call.id, "🎲 جاري جلب اقتراح رائع لك...")
        res = api.get_movies(page=random.randint(1, 5), limit=20)
        if res and res.get("status") == "success":
            movies = res.get("data", [])
            if movies:
                m = random.choice(movies)
                m_id = m['id']
                res_det = api.get_movie_details(m_id)
                if res_det and res_det.get("status") == "success":
                    m_data = res_det["data"]
                    title = m_data.get("title_ar") or m_data.get("title_en", "")
                    year = m_data.get("release_year", "N/A")
                    rating = m_data.get("rating", "N/A")
                    story = m_data.get("story") or "لا توجد قصة متاحة."
                    caption = f"🎲 <b>اقتراح اليوم العشوائي:</b>\n\n🎬 <b>{title}</b> ({year})\n⭐ التقييم: {rating}\n\n📝 <b>القصة:</b>\n<i>{story[:400]}</i>"

                    poster = m_data.get("poster")
                    poster_url = f"{api.BASE_MEDIA_URL}{poster}" if poster else None
                    keyboard = build_links_keyboard(m_data.get("watch_links", []), m_data.get("download_links", []), item_id=m_id, is_movie=True, user_id=user_id)

                    send_media_with_fallback(chat_id, call.message.message_id, poster_url, caption, keyboard)
                    return

        bot.send_message(chat_id, "❌ تعذر جلب اقتراح الآن، حاول لاحقاً.", reply_markup=get_main_keyboard(user_id == ADMIN_ID))

    # --- تقييم البوت ---
    elif data == "rate_bot_menu":
        bot.answer_callback_query(call.id)
        markup = types.InlineKeyboardMarkup(row_width=5)
        markup.add(
            types.InlineKeyboardButton("1 ⭐", callback_data="set_rate_1"),
            types.InlineKeyboardButton("2 ⭐", callback_data="set_rate_2"),
            types.InlineKeyboardButton("3 ⭐", callback_data="set_rate_3"),
            types.InlineKeyboardButton("4 ⭐", callback_data="set_rate_4"),
            types.InlineKeyboardButton("5 ⭐", callback_data="set_rate_5")
        )
        markup.add(types.InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu"))

        all_data = load_data()
        ratings = [u.get("rating", 0) for u in all_data.values() if u.get("rating", 0) > 0]
        avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else "لم يُقيّم بعد"

        rate_text = f"⭐ <b>تقييم بوت سينما Oscar TV:</b>\n\n📊 التقييم العام حالياً: <b>{avg_rating} / 5 🌟</b>\n\nيرجى اختيار تقييمك للبوت من الأزرار بالأسفل:"
        safe_edit_or_send(chat_id, call.message.message_id, rate_text, markup)

    elif data.startswith("set_rate_"):
        rate_val = int(data.split("_")[2])
        save_user_rating(user_id, rate_val)
        bot.answer_callback_query(call.id, f"🎉 شكراً لك! تم تسجيل تقييمك ({rate_val} نجوم) بنجاح.", show_alert=True)
        safe_edit_or_send(chat_id, call.message.message_id, "<b>🎬 القائمة الرئيسية:</b>", reply_markup=get_main_keyboard(user_id == ADMIN_ID))

    # --- لوحة تحكم الأدمن ---
    elif data in ["admin_panel_open", "admin_stats"]:
        if user_id != ADMIN_ID:
            return
        bot.answer_callback_query(call.id)
        u_data = load_data()
        msg_text = f"⚙️ <b>لوحة تحكم الأدمن:</b>\n\n👥 عدد الأعضاء المسجلين: <b>{len(u_data)}</b>"
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("📢 إذاعة للمستخدمين", callback_data="start_bc"),
            types.InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")
        )
        safe_edit_or_send(chat_id, call.message.message_id, msg_text, markup)

    elif data == "start_bc":
        if user_id != ADMIN_ID:
            return
        bot.answer_callback_query(call.id)
        msg = bot.send_message(chat_id, "📢 <b>أرسل الآن نص الإذاعة أو الصورة/الفيديو المطلوب إرساله للجميع:</b>")
        bot.register_next_step_handler(msg, start_broadcast_step)

    elif data == "main_menu":
        bot.answer_callback_query(call.id)
        safe_edit_or_send(chat_id, call.message.message_id, "<b>🎬 القائمة الرئيسية:</b>", reply_markup=get_main_keyboard(user_id == ADMIN_ID))

    elif data == "src_prompt":
        bot.answer_callback_query(call.id)
        msg = bot.send_message(chat_id, "🔍 <b>أدخل اسم الفيلم أو المسلسل للبحث:</b>")
        bot.register_next_step_handler(msg, process_search)

    elif data.startswith("jump_m_"):
        sort_by = data.split("_")[2]
        bot.answer_callback_query(call.id)
        msg = bot.send_message(chat_id, "🔢 <b>أدخل رقم صفحة الأفلام التي تريد الانتقال إليها:</b>")
        bot.register_next_step_handler(msg, process_jump_m, sort_by)

    elif data.startswith("jump_s_"):
        sort_by = data.split("_")[2]
        bot.answer_callback_query(call.id)
        msg = bot.send_message(chat_id, "🔢 <b>أدخل رقم صفحة المسلسلات التي تريد الانتقال إليها:</b>")
        bot.register_next_step_handler(msg, process_jump_s, sort_by)

    elif data == "show_favs":
        bot.answer_callback_query(call.id)
        favs = get_user_favs(user_id)
        m_favs, s_favs = favs.get("movies", {}), favs.get("series", {})

        if not m_favs and not s_favs:
            bot.send_message(chat_id, "❤️ <b>قائمة المفضلة لديك فارغة حالياً.</b>", reply_markup=get_main_keyboard(user_id == ADMIN_ID))
            return

        markup = types.InlineKeyboardMarkup(row_width=1)

        if m_favs:
            markup.add(types.InlineKeyboardButton("─── 🎬 الأفلام المفضلة ───", callback_data="noop"))
            for m_id, title in m_favs.items():
                markup.add(types.InlineKeyboardButton(f"📽️ {title}", callback_data=f"mdet_{m_id}"))

        if s_favs:
            markup.add(types.InlineKeyboardButton("─── 📺 المسلسلات المفضلة ───", callback_data="noop"))
            for s_id, title in s_favs.items():
                markup.add(types.InlineKeyboardButton(f"📺 {title}", callback_data=f"sdet_{s_id}"))

        markup.add(types.InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu"))
        bot.send_message(chat_id, "❤️ <b>قائمة المفضلة الخاصة بك:</b>", reply_markup=markup)

    elif data.startswith("tfav_"):
        parts = data.split("_")
        item_type, item_id = parts[1], str(parts[2])
        favs = get_user_favs(user_id)
        target_dict = favs["movies"] if item_type == "m" else favs["series"]

        if item_id in target_dict:
            target_dict.pop(item_id, None)
            bot.answer_callback_query(call.id, "💔 تم الإزالة من المفضلة!")
        else:
            title = "عنصر مفضل"
            if item_type == "m":
                details = api.get_movie_details(int(item_id))
                if details and details.get("status") == "success":
                    title = details["data"].get("title_ar") or details["data"].get("title_en", "فيلم")
            else:
                details = api.get_series_details(int(item_id))
                if details and details.get("status") == "success":
                    title = details["data"].get("title_ar") or details["data"].get("title_en", "مسلسل")

            target_dict[item_id] = title
            bot.answer_callback_query(call.id, "❤️ تم الإضافة إلى المفضلة!")

        save_user_favs(user_id, favs)

    elif data.startswith("mpage_"):
        parts = data.split("_")
        page = int(parts[1])
        sort_by = parts[2] if len(parts) > 2 else "most_viewed"

        bot.answer_callback_query(call.id, "جاري تحميل قائمة الأفلام...")
        res = api.get_movies(page=page, limit=20, sort_by=sort_by)

        if res and res.get("status") == "success":
            movies = res.get("data", [])
            if not movies and page > 1:
                bot.answer_callback_query(call.id, "⚠️ لا توجد أفلام أخرى، وصلت إلى نهاية القائمة.", show_alert=True)
                return

            keyboard = build_movies_keyboard(movies, page, sort_by)
            sort_title = "الأكثر مشاهدة 🔥" if sort_by == "most_viewed" else "الأحدث 🆕"
            safe_edit_or_send(chat_id, call.message.message_id, f"🎬 <b>قائمة الأفلام ({sort_title}) - صفحة {page}:</b>", keyboard)

    elif data.startswith("mdet_"):
        m_id = int(data.split("_")[1])
        bot.answer_callback_query(call.id, "جاري تحميل التفاصيل...")
        res = api.get_movie_details(m_id)

        if res and res.get("status") == "success":
            m = res["data"]
            title = m.get("title_ar") or m.get("title_en", "")
            year, rating = m.get("release_year", "N/A"), m.get("rating", "N/A")
            story = m.get("story") or "لا توجد قصة متاحة."
            genres = parse_genres(m.get("genres"))
            genres_str = f"\n🏷️ التصنيف: {genres}" if genres else ""

            caption = f"🎬 <b>{title}</b> ({year})\n⭐ التقييم: {rating}{genres_str}\n\n📝 <b>القصة:</b>\n<i>{story[:500]}</i>"
            poster = m.get("poster")
            poster_url = f"{api.BASE_MEDIA_URL}{poster}" if poster else None
            keyboard = build_links_keyboard(m.get("watch_links", []), m.get("download_links", []), item_id=m_id, is_movie=True, user_id=user_id)

            send_media_with_fallback(chat_id, call.message.message_id, poster_url, caption, keyboard)

    elif data.startswith("spage_"):
        parts = data.split("_")
        page = int(parts[1])
        sort_by = parts[2] if len(parts) > 2 else "most_viewed"

        bot.answer_callback_query(call.id, "جاري تحميل المسلسلات...")
        res = api.get_series(page=page, limit=20, sort_by=sort_by)

        if res and res.get("status") == "success":
            series_list = res.get("data", [])
            if not series_list and page > 1:
                bot.answer_callback_query(call.id, "⚠️ لا توجد مسلسلات أخرى، وصلت إلى نهاية القائمة.", show_alert=True)
                return

            keyboard = build_series_keyboard(series_list, page, sort_by)
            sort_title = "الأكثر مشاهدة 🔥" if sort_by == "most_viewed" else "الأحدث 🆕"
            safe_edit_or_send(chat_id, call.message.message_id, f"📺 <b>قائمة المسلسلات ({sort_title}) - صفحة {page}:</b>", keyboard)

    elif data.startswith("sdet_"):
        s_id = int(data.split("_")[1])
        bot.answer_callback_query(call.id, "جاري تحميل المسلسل والمواسم...")
        res = api.get_series_details(s_id)

        if res and res.get("status") == "success":
            s = res["data"]
            title = s.get("title_ar") or s.get("title_en", "")
            year, rating = s.get("release_year", "N/A"), s.get("rating", "N/A")
            story = s.get("story") or "لا توجد قصة متاحة."
            genres = parse_genres(s.get("genres"))
            genres_str = f"\n🏷️ التصنيف: {genres}" if genres else ""

            caption = f"📺 <b>{title}</b> ({year})\n⭐ التقييم: {rating}{genres_str}\n\n📝 <b>القصة:</b>\n<i>{story[:500]}</i>"
            poster = s.get("poster")
            poster_url = f"{api.BASE_MEDIA_URL}{poster}" if poster else None
            keyboard = build_series_details_keyboard(s, user_id)

            send_media_with_fallback(chat_id, call.message.message_id, poster_url, caption, keyboard)

    elif data.startswith("sn_"):
        parts = data.split("_")
        season_id = int(parts[1])
        page = int(parts[2]) if len(parts) > 2 else 1

        bot.answer_callback_query(call.id, "جاري تحميل الحلقات...")
        res = api.get_season_episodes(season_id=season_id, page=page, per_page=20)

        if res and res.get("status") == "success":
            episodes = res.get("data", [])
            if not episodes and page > 1:
                bot.answer_callback_query(call.id, "⚠️ لا توجد حلقات أخرى في هذا الموسم.", show_alert=True)
                return

            keyboard = build_episodes_keyboard(episodes, season_id, page, is_anime=False)
            safe_edit_or_send(chat_id, call.message.message_id, f"📁 <b>حلقات الموسم - صفحة {page}:</b>", keyboard)

    elif data.startswith("ep_"):
        ep_id = int(data.split("_")[1])
        bot.answer_callback_query(call.id, "جاري تحميل روابط الحلقة...")
        res = api.get_episode_details(ep_id)

        if res and res.get("status") == "success":
            ep = res["data"]
            series_title = ep.get("series_title") or ep.get("series_title_en", "المسلسل")
            ep_num = ep.get("episode_number", "?")
            caption = f"📺 <b>{series_title}</b> - الحلقة <b>{ep_num}</b>"

            thumb = ep.get("thumbnail") or ep.get("series_poster")
            thumb_url = f"{api.BASE_MEDIA_URL}{thumb}" if thumb and str(thumb).startswith("/") else thumb

            keyboard = build_links_keyboard(ep.get("watch_links", []), ep.get("download_links", []), is_movie=False)
            send_media_with_fallback(chat_id, call.message.message_id, thumb_url, caption, keyboard)


# ---------------------------------------------------------
# 8. تشغيل البوت
# ---------------------------------------------------------
if __name__ == "__main__":
    print("🤖 Bot is starting...")
    bot.infinity_polling(skip_pending=True)
