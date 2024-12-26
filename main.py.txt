import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import Conflict, NetworkError, TelegramError
import nest_asyncio
import sys
import random
from typing import Optional, Dict
from datetime import datetime, timedelta
import pickle
from special_cases_managerss import SpecialCasesManager
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import json
from datetime import datetime
from pathlib import Path


class SearchLogger:
    def __init__(self, log_file="search_logs.json"):
        self.log_file = log_file
        self.ensure_log_file_exists()

    def ensure_log_file_exists(self):
        # Create the file with an empty list if it doesn't exist or is empty
        if not Path(self.log_file).exists() or Path(self.log_file).stat().st_size == 0:
            with open(self.log_file, 'w') as f:
                json.dump([], f)

    def log_search(self, user_id: int, user_name: str, search_type: str, search_query: str):
        try:
            # First ensure the file exists and has valid JSON
            self.ensure_log_file_exists()

            # Read existing logs
            try:
                with open(self.log_file, 'r') as f:
                    logs = json.load(f)
            except json.JSONDecodeError:
                # If there's an error reading the JSON, start with an empty list
                logs = []

            # Create new log entry
            log_entry = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "user_id": user_id,
                "user_name": user_name,
                "search_type": search_type,
                "search_query": search_query
            }

            # Add new entry
            logs.append(log_entry)

            # Write back to file
            with open(self.log_file, 'w') as f:
                json.dump(logs, f, indent=2)

        except Exception as e:
            print(f"Error logging search: {e}")

    def get_recent_searches(self, limit: int = 100):
        try:
            # First ensure the file exists and has valid JSON
            self.ensure_log_file_exists()

            with open(self.log_file, 'r') as f:
                try:
                    logs = json.load(f)
                except json.JSONDecodeError:
                    return []
            return logs[-limit:]
        except Exception as e:
            print(f"Error getting recent searches: {e}")
            return []


# Create an instance of the logger
search_logger = SearchLogger()


# After your other global variables
special_cases_manager = SpecialCasesManager()

# Initialize some cases if you want (optional)
special_cases_manager.add_case(
    "pushpa 2",
    ["pushpa2", "pushpa-2", "pushpa2therule", "pushpa 2 the rule"],
    [
        {"url": "https://example4.com", "language": "Hindi"},
        {"url": "https://example5.com", "language": "Telugu"}
    ]
)

special_cases_manager.add_case(
    "venom",
    ["venom", "venom1", "venom2"],
    [
        {"url": "https://www.udlinks.com/3I1l", "language": "hindi"}
    ]
)




nest_asyncio.apply()

TELEGRAM_TOKEN = "7883754025:AAHUDU-_EM4QYome14k_28PQbPTWsl_9w6s"
TMDB_API_KEY = "c3b8704a4df65146c194940351efa9a2"
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
DELETE_TIMEOUT = 420  # 7 minutes in seconds
DISCLAIMER = "⚠️ This message will be deleted in 7 minutes"
HORROR_GENRE_ID = 27  # TMDB's genre ID for horror movies



USER_CONTEXT = {}

GENRE_IDS = {
    'horror': 27,
    'crime': 80,
    'romance': 10749
}


class TMDBAPIHandler:
    def __init__(self, api_key, base_url="https://api.themoviedb.org/3"):
        self.api_key = api_key
        self.base_url = base_url
        self.session = self._create_session()

    def _create_session(self):
        session = requests.Session()

        # Configure retry strategy
        retries = Retry(
            total=5,  # Total number of retries
            backoff_factor=0.5,  # Wait 0.5, 1, 2, 4, 8 seconds between retries
            status_forcelist=[500, 502, 503, 504, 408, 429]  # HTTP status codes to retry on
        )

        # Add retry adapter to session
        adapter = HTTPAdapter(max_retries=retries)
        session.mount('http://', adapter)
        session.mount('https://', adapter)

        return session

    def make_request(self, endpoint, params=None):
        if params is None:
            params = {}

        # Always include API key
        params['api_key'] = self.api_key

        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                response = self.session.get(
                    f"{self.base_url}{endpoint}",
                    params=params,
                    timeout=10  # 10 seconds timeout
                )
                response.raise_for_status()
                return response.json()

            except requests.exceptions.ConnectionError as e:
                if attempt == max_attempts - 1:
                    raise Exception("Unable to connect to TMDB API. Please check your internet connection.") from e
                time.sleep(2 ** attempt)  # Exponential backoff

            except requests.exceptions.Timeout as e:
                if attempt == max_attempts - 1:
                    raise Exception("TMDB API request timed out. Please try again later.") from e
                time.sleep(2 ** attempt)

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:  # Rate limit exceeded
                    retry_after = int(e.response.headers.get('Retry-After', 5))
                    time.sleep(retry_after)
                    continue
                raise Exception(f"TMDB API error: {e.response.status_code}") from e


LAST_ACTIVITY_FILE = "user_activity.pkl"
INACTIVITY_THRESHOLD = timedelta(hours=78)


class SearchStatistics:
    def __init__(self, log_file="search_logs.json", stats_file="stastics.txt"):
        self.log_file = log_file
        self.stats_file = stats_file
        self.search_logger = SearchLogger(log_file)
        # Ensure stastics file exists
        self.update_stastics_file()
        print(f"SearchStatistics initialized. Stats file: {stats_file}")

    def _load_searches(self):
        """Load searches from the log file"""
        try:
            with open(self.log_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def get_most_searched(self, days=None):
        """Get most searched queries within specified days"""
        searches = self._load_searches()
        if not searches:
            return []

        # Filter by date if days is specified
        if days:
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            searches = [s for s in searches if s['timestamp'][:10] >= cutoff_date]

        # Count search queries
        query_counts = {}
        for search in searches:
            query = search['search_query'].lower()
            query_counts[query] = query_counts.get(query, 0) + 1

        # Sort by count and return top 10
        return sorted(query_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    def get_user_search_history(self, limit=50):
        """Get recent user search history"""
        searches = self._load_searches()
        return searches[-limit:] if searches else []

    def update_stastics_file(self):  # Changed method name to match file name
        try:
            print(f"Updating stastics file at {datetime.now()}")

            # Check if log file exists and has data
            if not Path(self.log_file).exists():
                print(f"Log file {self.log_file} does not exist!")
                return

            # Load searches
            searches = self._load_searches()
            if not searches:
                print("No search data found in logs")
                stats_text = "No search data available yet.\nLast Updated: " + datetime.now().strftime(
                    '%Y-%m-%d %H:%M:%S')
            else:
                # Get statistics for different time periods
                all_time = self.get_most_searched()
                today = self.get_most_searched(days=1)
                week = self.get_most_searched(days=7)
                year = self.get_most_searched(days=365)
                user_history = self.get_user_search_history(limit=50)

                stats_text = self._format_stastics(all_time, today, week, year, user_history)  # Changed method name

            # Write to stastics file
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                f.write(stats_text)

            print(f"Stastics file updated successfully at {datetime.now()}")

            # Debug: Read and print file contents
            with open(self.stats_file, 'r', encoding='utf-8') as f:
                content = f.read()
            print(f"Stastics file size: {len(content)} bytes")

        except Exception as e:
            print(f"Error updating stastics file: {e}")
            import traceback
            traceback.print_exc()

    def _format_stastics(self, all_time, today, week, year, user_history):  # Changed method name
        stats_text = "Movie Search Stastics\n"  # Changed heading
        stats_text += "=" * 50 + "\n\n"

        # Add section for each time period
        sections = [
            ("All-Time Most Searched Movies:", all_time),
            ("Today's Most Searched Movies:", today),
            ("This Week's Most Searched Movies:", week),
            ("This Year's Most Searched Movies:", year)
        ]

        for title, data in sections:
            stats_text += f"{title}\n"
            if data:
                stats_text += "\n".join(f"{i + 1}. {movie} ({count} searches)"
                                      for i, (movie, count) in enumerate(data))
            else:
                stats_text += "No searches in this period"
            stats_text += "\n\n"

        # Add user history section
        stats_text += "Recent User Search History:\n"
        stats_text += "=" * 50 + "\n"
        if user_history:
            for search in user_history:
                stats_text += f"\nTime: {search['timestamp']}\n"
                stats_text += f"User: {search['user_name']} (ID: {search['user_id']})\n"
                stats_text += f"Search Type: {search['search_type']}\n"
                stats_text += f"Query: {search['search_query']}\n"
                stats_text += "-" * 30 + "\n"
        else:
            stats_text += "\nNo user search history available yet\n"

        stats_text += f"\nLast Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        return stats_text

# Modify the update_statistics_job to include error handling and logging
async def update_stastics_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        print(f"Starting stastics update job at {datetime.now()}")
        stats = SearchStatistics()
        stats.update_stastics_file()
        print(f"Completed stastics update job at {datetime.now()}")
    except Exception as e:
        print(f"Error in stastics update job: {e}")
        import traceback
        traceback.print_exc()

async def view_searches_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only allow yourself to see the searches
    if update.message.from_user.id == 6822829183:  # Replace with your Telegram ID
        recent_searches = search_logger.get_recent_searches(limit=10)  # Get last 10 searches

        message = "Recent Searches:\n\n"
        for search in recent_searches:
            message += f"👤 User: {search['user_name']}\n"
            message += f"🔍 Query: {search['search_query']}\n"
            message += f"⏰ Time: {search['timestamp']}\n"
            message += f"Type: {search['search_type']}\n\n"

        await update.message.reply_text(message)
    else:
        await update.message.reply_text("You don't have permission to use this command.")


# Add this to your command handlers

class UserActivityManager:
    def __init__(self):
        self.user_activity = {}
        self.load_activity()

    def load_activity(self):
        if Path(LAST_ACTIVITY_FILE).exists():
            try:
                with open(LAST_ACTIVITY_FILE, 'rb') as f:
                    self.user_activity = pickle.load(f)
            except Exception as e:
                print(f"Error loading user activity: {e}")
                self.user_activity = {}

    def save_activity(self):
        try:
            with open(LAST_ACTIVITY_FILE, 'wb') as f:
                pickle.dump(self.user_activity, f)
        except Exception as e:
            print(f"Error saving user activity: {e}")

    def update_user_activity(self, user_id: int, user_name: str):
        self.user_activity[user_id] = {
            'last_active': datetime.now(),
            'name': user_name
        }
        self.save_activity()

    def get_inactive_users(self):
        current_time = datetime.now()
        inactive_users = []

        for user_id, data in self.user_activity.items():
            if (current_time - data['last_active']) >= INACTIVITY_THRESHOLD:
                inactive_users.append({
                    'user_id': user_id,
                    'name': data['name'],
                    'last_active': data['last_active']
                })

        return inactive_users


# Create global instance
activity_manager = UserActivityManager()


# Modify the handle_user_message function to track activity
async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    await delete_message_later(context, update.message.chat_id, update.message.message_id)
    await handle_user_query(update, context)


# Add a new function to check for inactive users
async def check_inactive_users(context: ContextTypes.DEFAULT_TYPE):
    inactive_users = activity_manager.get_inactive_users()

    for user in inactive_users:
        try:
            message = f"Hey {user['name']} 👋,\n\nI am missing you dear! 💫\nIt's been a while since we last chatted. Come back and discover some amazing movies! 🎬"

            await context.bot.send_message(
                chat_id=user['user_id'],
                text=message,
                parse_mode='Markdown'
            )

            # Update the last activity to prevent spam
            activity_manager.update_user_activity(user['user_id'], user['name'])

        except Exception as e:
            print(f"Error sending reminder to user {user['user_id']}: {e}")

class MessageTracker:
    def __init__(self):
        self.messages: Dict[int, Dict[int, datetime]] = {}

    async def add_message(self, chat_id: int, message_id: int):
        if chat_id not in self.messages:
            self.messages[chat_id] = {}
        self.messages[chat_id][message_id] = datetime.now() + timedelta(seconds=DELETE_TIMEOUT)

    async def cleanup_messages(self, context: ContextTypes.DEFAULT_TYPE):
        current_time = datetime.now()
        for chat_id in list(self.messages.keys()):
            for message_id, expiry_time in list(self.messages[chat_id].items()):
                if current_time >= expiry_time:
                    try:
                        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                    except TelegramError:
                        pass  # Message might already be deleted
                    finally:
                        del self.messages[chat_id][message_id]
            if not self.messages[chat_id]:
                del self.messages[chat_id]

message_tracker = MessageTracker()

async def cleanup_job(context: ContextTypes.DEFAULT_TYPE):
    await message_tracker.cleanup_messages(context)

async def delete_message_later(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int):
    await message_tracker.add_message(chat_id, message_id)

async def send_with_warning(message, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None, parse_mode=None):
    try:
        if hasattr(message, 'reply_text'):
            sent_message = await message.reply_text(
                f"{text}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await message.edit_text(
                f"{text}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

        await delete_message_later(context, sent_message.chat_id, sent_message.message_id)
        return sent_message
    except TelegramError as e:
        print(f"Error sending message: {e}")
        return None

async def send_photo_with_warning(message, context: ContextTypes.DEFAULT_TYPE, photo: str, caption: str, reply_markup=None, parse_mode=None):
    try:
        if hasattr(message, 'reply_photo'):
            sent_message = await message.reply_photo(
                photo=photo,
                caption=f"{caption}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await context.bot.send_photo(
                chat_id=message.chat_id,
                photo=photo,
                caption=f"{caption}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

        await delete_message_later(context, sent_message.chat_id, sent_message.message_id)
        return sent_message
    except TelegramError as e:
        print(f"Error sending photo: {e}")
        return None


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    keyboard = [
        [InlineKeyboardButton("  DOWNLOAD MOVIES", callback_data='search_movies')],
        [
            InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
            InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
            InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
        ],
        [InlineKeyboardButton("📈 Popular Movies", callback_data='popular'),
         InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
        [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
        [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_with_warning(
        update.message,
        context,
        f"👋 Hello {user_name}! Welcome to @movieshuba11_bot!\n\nClick on /start to restart or type",
        reply_markup=reply_markup
    )

async def show_start_menu(message, context: ContextTypes.DEFAULT_TYPE):
    # Get user's name from the callback query
    user_name = message._effective_user.first_name if hasattr(message, '_effective_user') else "there"
    keyboard = [
        [InlineKeyboardButton(" Download movies", callback_data='search_movies')],
        [
            InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
            InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
            InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
        ],
        [InlineKeyboardButton("📈 Popular Movies", callback_data='popular')],
        [InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
        [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
        [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_with_warning(
        message,
        context,
        f"👋 Hello {user_name}! Welcome to moviieshubb_bot!\n\nClick on /start to restart or type",
        reply_markup=reply_markup
    )



async def get_random_movies_by_genre(message, context: ContextTypes.DEFAULT_TYPE, genre_id=None):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "sort_by": "popularity.desc",
            "page": 1
        }

        if genre_id:
            params["with_genres"] = genre_id

        response = requests.get(url, params=params)
        response.raise_for_status()
        total_pages = min(response.json().get("total_pages", 1), 500)

        random_page = random.randint(1, total_pages)
        params["page"] = random_page

        response = requests.get(url, params=params)
        response.raise_for_status()

        all_movies = response.json().get("results", [])
        random_movies = random.sample(all_movies, min(5, len(all_movies)))

        response_text = "🎲 Random Movie Suggestions:\n\n"
        keyboard = []
        for i, movie in enumerate(random_movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"
            keyboard.append([InlineKeyboardButton(f"🔍 Search {movie['title']}", callback_data=f'search_specific_{movie["id"]}')])

        keyboard.extend([
            [
                InlineKeyboardButton("👻 Horror", callback_data='random_horror'),
                InlineKeyboardButton("🔪 Crime", callback_data='random_crime'),
                InlineKeyboardButton("💝 Romance", callback_data='random_romance')
            ],
            [InlineKeyboardButton("🎲 More Random", callback_data='random_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching random movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='random_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                                "Sorry, couldn't fetch random movies right now.",
                                reply_markup=reply_markup)


async def get_popular_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/movie/popular"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "🎬 Currently Popular Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching popular movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='popular')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch popular movies right now.",
                              reply_markup=reply_markup)

async def get_horror_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "with_genres": HORROR_GENRE_ID,
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "👻 Popular Horror Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton("👻 More Horror Movies", callback_data='horror_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching horror movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='horror_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch horror movies right now.",
                              reply_markup=reply_markup)

async def get_bollywood_popular_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "region": "IN",
            "with_original_language": "hi",
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "🎬  Bollywood Popular Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching Bollywood movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='bollywood_popular')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch Bollywood movies right now.",
                              reply_markup=reply_markup)


async def search_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    special_case, special_links = special_cases_manager.is_special_case(query)
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Log the search
    search_logger.log_search(user_id, user_name, "movie", query)
    try:
        tmdb_handler = TMDBAPIHandler(TMDB_API_KEY)

        # Search for movie
        results = tmdb_handler.make_request(
            "/search/movie",
            params={"query": query, "language": "en-US"}
        ).get("results", [])

        if results:
            movie = results[0]
            movie_id = movie["id"]

            # Get movie details
            movie_details = tmdb_handler.make_request(f"/movie/{movie_id}")
            providers = tmdb_handler.make_request(f"/movie/{movie_id}/watch/providers").get("results", {}).get("US",
                                                                                                               {}).get(
                "flatrate", [])

        search_url = f"{TMDB_BASE_URL}/search/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        if results:
            movie = results[0]
            movie_id = movie["id"]

            details_url = f"{TMDB_BASE_URL}/movie/{movie_id}"
            watch_providers_url = f"{TMDB_BASE_URL}/movie/{movie_id}/watch/providers"

            details_response = requests.get(details_url, params={"api_key": TMDB_API_KEY})
            providers_response = requests.get(watch_providers_url, params={"api_key": TMDB_API_KEY})

            movie_details = details_response.json()
            providers = providers_response.json().get("results", {}).get("US", {}).get("flatrate", [])

            keyboard = [
                [InlineKeyboardButton(" Search Another Movie", callback_data='search_movies')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            response_text = (
                f"*{movie_details['title']}* ({movie_details.get('release_date', '')[:4]})\n\n"
                f"Plot: {movie_details.get('overview', 'No plot available')}\n\n"
            )

            if providers:
                response_text += "Available on: " + ", ".join(p["provider_name"] for p in providers) + "\n\n"
            else:
                response_text += "Streaming information not available\n\n"

            if special_case and special_links:
                response_text += "Download Links:\n"
                for link in special_links:
                    lang_text = f" ({link['language']})" if link.get('language') else ""
                    response_text += f"• {link['url']}{lang_text}\n"
            else:
                response_text += "download link comming soon msg @balaram129"

            if movie_details.get("poster_path"):
                poster_url = f"{TMDB_IMAGE_BASE_URL}{movie_details['poster_path']}"
                await send_photo_with_warning(update.message, context, photo=poster_url, caption=response_text, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                await send_with_warning(update.message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            keyboard = [
                [InlineKeyboardButton(" Try Again", callback_data='search_movies')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(update.message, context, "No movies found matching your search.", reply_markup=reply_markup)
    except Exception as e:
        print(f"Error in movie search: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(update.message, context,
                              "Sorry, there was an error processing your request. Please try again.",
                              reply_markup=reply_markup)

async def search_by_actor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Log the search
    search_logger.log_search(user_id, user_name, "actor", query)
    try:
        search_url = f"{TMDB_BASE_URL}/search/person"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        if results:
            actor = results[0]
            actor_id = actor["id"]

            actor_details_url = f"{TMDB_BASE_URL}/person/{actor_id}"
            movies_url = f"{TMDB_BASE_URL}/person/{actor_id}/movie_credits"

            actor_details_response = requests.get(actor_details_url, params={"api_key": TMDB_API_KEY})
            movies_response = requests.get(movies_url, params={"api_key": TMDB_API_KEY})

            actor_details = actor_details_response.json()
            movies = movies_response.json().get("cast", [])

            movies_with_rating = [m for m in movies if m.get("vote_average", 0) > 0]
            sorted_movies = sorted(movies_with_rating, key=lambda x: x.get("vote_average", 0), reverse=True)

            popular_movies = [m for m in sorted_movies if m.get("vote_average", 0) >= 7][:4]
            unpopular_movies = [m for m in sorted_movies if m.get("vote_average", 0) < 7][:4]

            response_text = f"🎭 {actor['name']}\n"
            if actor_details.get("birthday"):
                response_text += f"Birthday: {actor_details['birthday']}\n"
            if actor_details.get("place_of_birth"):
                response_text += f"Birthplace: {actor_details['place_of_birth']}\n"

            response_text += "\n📈 Highly Rated Movies:\n"
            for i, movie in enumerate(popular_movies, 1):
                response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
                response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"

            response_text += "\n📉 Other Notable Movies:\n"
            for i, movie in enumerate(unpopular_movies, 1):
                response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
                response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"

            keyboard = [
                [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
                [InlineKeyboardButton(" Search Another Actor", callback_data='search_actor')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            if actor.get("profile_path"):
                actor_image_url = f"{TMDB_IMAGE_BASE_URL}{actor['profile_path']}"
                await send_photo_with_warning(
                    update.message,
                    context,
                    photo=actor_image_url,
                    caption=response_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await send_with_warning(
                    update.message,
                    context,
                    response_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
        else:
            keyboard = [
                [InlineKeyboardButton(" Try Again", callback_data='search_actor')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                update.message,
                context,
                "No actor found matching your search.",
                reply_markup=reply_markup
            )
    except Exception as e:
        print(f"Error in actor search: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='search_actor')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(
            update.message,
            context,
            "Sorry, there was an error processing your request. Please try again.",
            reply_markup=reply_markup
        )
def is_special_case(query):
    query_lower = query.lower().strip()
    for key, case in special_cases_manager.items():
        if query_lower == key.lower() or query_lower in [v.lower() for v in case["variants"]]:
            return True, case["links"]
    return False, []

async def get_genre_movies(message, context: ContextTypes.DEFAULT_TYPE, genre_id: int, genre_name: str):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "with_genres": genre_id,
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = f"🎬 Popular {genre_name} Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching {genre_name} movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data=f'genre_{genre_name.lower()}')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              f"Sorry, couldn't fetch {genre_name} movies right now.",
                              reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_name = query.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    try:
        if query.data.startswith('search_specific_'):
            movie_id = query.data.split('_')[2]
            # Get movie details from TMDB
            url = f"{TMDB_BASE_URL}/movie/{movie_id}"
            response = requests.get(url, params={"api_key": TMDB_API_KEY})
            movie = response.json()

            # Create a message with movie details
            movie_text = f"{movie['title']} ({movie.get('release_date', '')[:4]})"

            # Send a temporary message to user's private chat
            class SimulatedMessage:
                def __init__(self, chat_id, text, from_user):
                    self.chat_id = chat_id
                    self.text = text
                    self.from_user = from_user

                def reply_text(self, *args, **kwargs):
                    return query.message.reply_text(*args, **kwargs)

                def reply_photo(self, *args, **kwargs):
                    return query.message.reply_photo(*args, **kwargs)

            # Create a proper message object
            simulated_message = SimulatedMessage(
                chat_id=query.message.chat_id,
                text=movie['title'],
                from_user=query.from_user
            )

            # Create a proper update object
            class SimulatedUpdate:
                def __init__(self, message):
                    self.message = message

            simulated_update = SimulatedUpdate(simulated_message)

            # Perform the search
            await search_movie(simulated_update, context)
            return
        if query.data == 'genre_horror':
            await get_genre_movies(query.message, context, GENRE_IDS['horror'], "Horror")
        elif query.data == 'genre_romance':
            await get_genre_movies(query.message, context, GENRE_IDS['romance'], "Romance")
        elif query.data == 'genre_crime':
            await get_genre_movies(query.message, context, GENRE_IDS['crime'], "Crime")
        elif query.data == 'random_movies':
            await get_random_movies_by_genre(query.message, context)
        if query.data == 'random_movies':
            await get_random_movies_by_genre(query.message, context)
        elif query.data == 'random_horror':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['horror'])
        elif query.data == 'random_crime':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['crime'])
        elif query.data == 'random_romance':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['romance'])
        elif query.data == 'horror_movies':
            await get_horror_movies(query.message, context)
        elif query.data == 'search_movies':
            USER_CONTEXT[query.message.chat_id] = 'movie'
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "🔍 Just type the name of any movie you want to search for!",
                reply_markup=reply_markup
            )
        elif query.data == 'search_actor':
            USER_CONTEXT[query.message.chat_id] = 'actor'
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "🎭 Just type the name of any actor to see their movies!",
                reply_markup=reply_markup
            )
        elif query.data == 'help':
            help_text = ("📖 How to use this bot:\n\n"
                        "1. Simply type any movie name\n"
                        "2. Or type any actor name to find their movies\n"
                        "3. I'll show you the details\n"
                        "4. Check out popular movies in both Hollywood and Bollywood\n"
                        "5. Try our random movie suggestions by genre!\n"
                        "Need more help? Just type /start to see the main menu again! or msg @balaram129")
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                help_text,
                reply_markup=reply_markup
            )
        elif query.data == 'popular':
            await get_popular_movies(query.message, context)
        elif query.data == 'bollywood_popular':
            await get_bollywood_popular_movies(query.message, context)
        elif query.data == 'start_menu':
            keyboard = [
                [InlineKeyboardButton("🔍 Download movies", callback_data='search_movies'),
                 InlineKeyboardButton("👻 Horror Movies", callback_data='horror_movies')],
                [
                    InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
                    InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
                    InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
                ],
                [InlineKeyboardButton("📈 Popular Movies", callback_data='popular')],
                [InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
                [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
                [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
                [InlineKeyboardButton("❓ Help", callback_data='help')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "👋 Welcome to moviieshubb_bot!\n\nClick on /start to restart or type",
                reply_markup=reply_markup
            )

    except Exception as e:
        print(f"Error in button callback: {e}")
        keyboard = [
            [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(
            query.message,
            context,
            "Sorry, there was an error processing your request. Please try again.",
            reply_markup=reply_markup
        )

async def handle_user_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_context = USER_CONTEXT.get(update.message.chat_id, "movie")
    if user_context == "actor":
        await search_by_actor(update, context)
    else:
        await search_movie(update, context)

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_message_later(context, update.message.chat_id, update.message.message_id)
    await handle_user_query(update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Exception while handling an update: {context.error}")
    if isinstance(context.error, Conflict):
        print("Bot instance already running. Exiting...")
        sys.exit(1)
    elif isinstance(context.error, NetworkError):
        print("Network error occurred. Waiting before retry...")
        await asyncio.sleep(1)
    else:
        print(f"Unexpected error: {context.error}")


def main():
    try:
        application = (
            Application.builder()
            .token(TELEGRAM_TOKEN)
            .build()
        )

        # Add existing handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CallbackQueryHandler(button_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))
        application.add_handler(CommandHandler("viewsearches", view_searches_command))

        # Add error handler
        application.add_error_handler(error_handler)

        # Set up the cleanup job to run every 10 seconds
        job_queue = application.job_queue
        job_queue.run_repeating(cleanup_job, interval=10, first=0)

        # Add the inactive user check job (runs every 6 hours)
        job_queue.run_repeating(check_inactive_users, interval=21600, first=21600)

        # Update stastics more frequently (every 5 minutes)
        job_queue.run_repeating(update_stastics_job, interval=300, first=0)

        # Initial statistics update
        print("Performing initial statistics update...")
        stats = SearchStatistics()
        stats.update_stastics_file()
        print("Initial statistics update completed")

        # Start the bot
        print("Starting bot...")
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

    except Exception as e:
        print(f"Error starting bot: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

# Test the logger
logger = SearchLogger()
logger.log_search(123456, "TestUser", "movie", "Avatar")

# Check recent searches
recent = logger.get_recent_searches()
print("Recent searches:", recent)import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import Conflict, NetworkError, TelegramError
import nest_asyncio
import sys
import random
from typing import Optional, Dict
from datetime import datetime, timedelta
import pickle
from special_cases_managerss import SpecialCasesManager
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import json
from datetime import datetime
from pathlib import Path


class SearchLogger:
    def __init__(self, log_file="search_logs.json"):
        self.log_file = log_file
        self.ensure_log_file_exists()

    def ensure_log_file_exists(self):
        # Create the file with an empty list if it doesn't exist or is empty
        if not Path(self.log_file).exists() or Path(self.log_file).stat().st_size == 0:
            with open(self.log_file, 'w') as f:
                json.dump([], f)

    def log_search(self, user_id: int, user_name: str, search_type: str, search_query: str):
        try:
            # First ensure the file exists and has valid JSON
            self.ensure_log_file_exists()

            # Read existing logs
            try:
                with open(self.log_file, 'r') as f:
                    logs = json.load(f)
            except json.JSONDecodeError:
                # If there's an error reading the JSON, start with an empty list
                logs = []

            # Create new log entry
            log_entry = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "user_id": user_id,
                "user_name": user_name,
                "search_type": search_type,
                "search_query": search_query
            }

            # Add new entry
            logs.append(log_entry)

            # Write back to file
            with open(self.log_file, 'w') as f:
                json.dump(logs, f, indent=2)

        except Exception as e:
            print(f"Error logging search: {e}")

    def get_recent_searches(self, limit: int = 100):
        try:
            # First ensure the file exists and has valid JSON
            self.ensure_log_file_exists()

            with open(self.log_file, 'r') as f:
                try:
                    logs = json.load(f)
                except json.JSONDecodeError:
                    return []
            return logs[-limit:]
        except Exception as e:
            print(f"Error getting recent searches: {e}")
            return []


# Create an instance of the logger
search_logger = SearchLogger()


# After your other global variables
special_cases_manager = SpecialCasesManager()

# Initialize some cases if you want (optional)
special_cases_manager.add_case(
    "pushpa 2",
    ["pushpa2", "pushpa-2", "pushpa2therule", "pushpa 2 the rule"],
    [
        {"url": "https://example4.com", "language": "Hindi"},
        {"url": "https://example5.com", "language": "Telugu"}
    ]
)

special_cases_manager.add_case(
    "venom",
    ["venom", "venom1", "venom2"],
    [
        {"url": "https://www.udlinks.com/3I1l", "language": "hindi"}
    ]
)




nest_asyncio.apply()

TELEGRAM_TOKEN = "7883754025:AAHUDU-_EM4QYome14k_28PQbPTWsl_9w6s"
TMDB_API_KEY = "c3b8704a4df65146c194940351efa9a2"
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
DELETE_TIMEOUT = 420  # 7 minutes in seconds
DISCLAIMER = "⚠️ This message will be deleted in 7 minutes"
HORROR_GENRE_ID = 27  # TMDB's genre ID for horror movies



USER_CONTEXT = {}

GENRE_IDS = {
    'horror': 27,
    'crime': 80,
    'romance': 10749
}


class TMDBAPIHandler:
    def __init__(self, api_key, base_url="https://api.themoviedb.org/3"):
        self.api_key = api_key
        self.base_url = base_url
        self.session = self._create_session()

    def _create_session(self):
        session = requests.Session()

        # Configure retry strategy
        retries = Retry(
            total=5,  # Total number of retries
            backoff_factor=0.5,  # Wait 0.5, 1, 2, 4, 8 seconds between retries
            status_forcelist=[500, 502, 503, 504, 408, 429]  # HTTP status codes to retry on
        )

        # Add retry adapter to session
        adapter = HTTPAdapter(max_retries=retries)
        session.mount('http://', adapter)
        session.mount('https://', adapter)

        return session

    def make_request(self, endpoint, params=None):
        if params is None:
            params = {}

        # Always include API key
        params['api_key'] = self.api_key

        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                response = self.session.get(
                    f"{self.base_url}{endpoint}",
                    params=params,
                    timeout=10  # 10 seconds timeout
                )
                response.raise_for_status()
                return response.json()

            except requests.exceptions.ConnectionError as e:
                if attempt == max_attempts - 1:
                    raise Exception("Unable to connect to TMDB API. Please check your internet connection.") from e
                time.sleep(2 ** attempt)  # Exponential backoff

            except requests.exceptions.Timeout as e:
                if attempt == max_attempts - 1:
                    raise Exception("TMDB API request timed out. Please try again later.") from e
                time.sleep(2 ** attempt)

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:  # Rate limit exceeded
                    retry_after = int(e.response.headers.get('Retry-After', 5))
                    time.sleep(retry_after)
                    continue
                raise Exception(f"TMDB API error: {e.response.status_code}") from e


LAST_ACTIVITY_FILE = "user_activity.pkl"
INACTIVITY_THRESHOLD = timedelta(hours=78)


class SearchStatistics:
    def __init__(self, log_file="search_logs.json", stats_file="stastics.txt"):
        self.log_file = log_file
        self.stats_file = stats_file
        self.search_logger = SearchLogger(log_file)
        # Ensure stastics file exists
        self.update_stastics_file()
        print(f"SearchStatistics initialized. Stats file: {stats_file}")

    def _load_searches(self):
        """Load searches from the log file"""
        try:
            with open(self.log_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def get_most_searched(self, days=None):
        """Get most searched queries within specified days"""
        searches = self._load_searches()
        if not searches:
            return []

        # Filter by date if days is specified
        if days:
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            searches = [s for s in searches if s['timestamp'][:10] >= cutoff_date]

        # Count search queries
        query_counts = {}
        for search in searches:
            query = search['search_query'].lower()
            query_counts[query] = query_counts.get(query, 0) + 1

        # Sort by count and return top 10
        return sorted(query_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    def get_user_search_history(self, limit=50):
        """Get recent user search history"""
        searches = self._load_searches()
        return searches[-limit:] if searches else []

    def update_stastics_file(self):  # Changed method name to match file name
        try:
            print(f"Updating stastics file at {datetime.now()}")

            # Check if log file exists and has data
            if not Path(self.log_file).exists():
                print(f"Log file {self.log_file} does not exist!")
                return

            # Load searches
            searches = self._load_searches()
            if not searches:
                print("No search data found in logs")
                stats_text = "No search data available yet.\nLast Updated: " + datetime.now().strftime(
                    '%Y-%m-%d %H:%M:%S')
            else:
                # Get statistics for different time periods
                all_time = self.get_most_searched()
                today = self.get_most_searched(days=1)
                week = self.get_most_searched(days=7)
                year = self.get_most_searched(days=365)
                user_history = self.get_user_search_history(limit=50)

                stats_text = self._format_stastics(all_time, today, week, year, user_history)  # Changed method name

            # Write to stastics file
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                f.write(stats_text)

            print(f"Stastics file updated successfully at {datetime.now()}")

            # Debug: Read and print file contents
            with open(self.stats_file, 'r', encoding='utf-8') as f:
                content = f.read()
            print(f"Stastics file size: {len(content)} bytes")

        except Exception as e:
            print(f"Error updating stastics file: {e}")
            import traceback
            traceback.print_exc()

    def _format_stastics(self, all_time, today, week, year, user_history):  # Changed method name
        stats_text = "Movie Search Stastics\n"  # Changed heading
        stats_text += "=" * 50 + "\n\n"

        # Add section for each time period
        sections = [
            ("All-Time Most Searched Movies:", all_time),
            ("Today's Most Searched Movies:", today),
            ("This Week's Most Searched Movies:", week),
            ("This Year's Most Searched Movies:", year)
        ]

        for title, data in sections:
            stats_text += f"{title}\n"
            if data:
                stats_text += "\n".join(f"{i + 1}. {movie} ({count} searches)"
                                      for i, (movie, count) in enumerate(data))
            else:
                stats_text += "No searches in this period"
            stats_text += "\n\n"

        # Add user history section
        stats_text += "Recent User Search History:\n"
        stats_text += "=" * 50 + "\n"
        if user_history:
            for search in user_history:
                stats_text += f"\nTime: {search['timestamp']}\n"
                stats_text += f"User: {search['user_name']} (ID: {search['user_id']})\n"
                stats_text += f"Search Type: {search['search_type']}\n"
                stats_text += f"Query: {search['search_query']}\n"
                stats_text += "-" * 30 + "\n"
        else:
            stats_text += "\nNo user search history available yet\n"

        stats_text += f"\nLast Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        return stats_text

# Modify the update_statistics_job to include error handling and logging
async def update_stastics_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        print(f"Starting stastics update job at {datetime.now()}")
        stats = SearchStatistics()
        stats.update_stastics_file()
        print(f"Completed stastics update job at {datetime.now()}")
    except Exception as e:
        print(f"Error in stastics update job: {e}")
        import traceback
        traceback.print_exc()

async def view_searches_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only allow yourself to see the searches
    if update.message.from_user.id == 6822829183:  # Replace with your Telegram ID
        recent_searches = search_logger.get_recent_searches(limit=10)  # Get last 10 searches

        message = "Recent Searches:\n\n"
        for search in recent_searches:
            message += f"👤 User: {search['user_name']}\n"
            message += f"🔍 Query: {search['search_query']}\n"
            message += f"⏰ Time: {search['timestamp']}\n"
            message += f"Type: {search['search_type']}\n\n"

        await update.message.reply_text(message)
    else:
        await update.message.reply_text("You don't have permission to use this command.")


# Add this to your command handlers

class UserActivityManager:
    def __init__(self):
        self.user_activity = {}
        self.load_activity()

    def load_activity(self):
        if Path(LAST_ACTIVITY_FILE).exists():
            try:
                with open(LAST_ACTIVITY_FILE, 'rb') as f:
                    self.user_activity = pickle.load(f)
            except Exception as e:
                print(f"Error loading user activity: {e}")
                self.user_activity = {}

    def save_activity(self):
        try:
            with open(LAST_ACTIVITY_FILE, 'wb') as f:
                pickle.dump(self.user_activity, f)
        except Exception as e:
            print(f"Error saving user activity: {e}")

    def update_user_activity(self, user_id: int, user_name: str):
        self.user_activity[user_id] = {
            'last_active': datetime.now(),
            'name': user_name
        }
        self.save_activity()

    def get_inactive_users(self):
        current_time = datetime.now()
        inactive_users = []

        for user_id, data in self.user_activity.items():
            if (current_time - data['last_active']) >= INACTIVITY_THRESHOLD:
                inactive_users.append({
                    'user_id': user_id,
                    'name': data['name'],
                    'last_active': data['last_active']
                })

        return inactive_users


# Create global instance
activity_manager = UserActivityManager()


# Modify the handle_user_message function to track activity
async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    await delete_message_later(context, update.message.chat_id, update.message.message_id)
    await handle_user_query(update, context)


# Add a new function to check for inactive users
async def check_inactive_users(context: ContextTypes.DEFAULT_TYPE):
    inactive_users = activity_manager.get_inactive_users()

    for user in inactive_users:
        try:
            message = f"Hey {user['name']} 👋,\n\nI am missing you dear! 💫\nIt's been a while since we last chatted. Come back and discover some amazing movies! 🎬"

            await context.bot.send_message(
                chat_id=user['user_id'],
                text=message,
                parse_mode='Markdown'
            )

            # Update the last activity to prevent spam
            activity_manager.update_user_activity(user['user_id'], user['name'])

        except Exception as e:
            print(f"Error sending reminder to user {user['user_id']}: {e}")

class MessageTracker:
    def __init__(self):
        self.messages: Dict[int, Dict[int, datetime]] = {}

    async def add_message(self, chat_id: int, message_id: int):
        if chat_id not in self.messages:
            self.messages[chat_id] = {}
        self.messages[chat_id][message_id] = datetime.now() + timedelta(seconds=DELETE_TIMEOUT)

    async def cleanup_messages(self, context: ContextTypes.DEFAULT_TYPE):
        current_time = datetime.now()
        for chat_id in list(self.messages.keys()):
            for message_id, expiry_time in list(self.messages[chat_id].items()):
                if current_time >= expiry_time:
                    try:
                        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                    except TelegramError:
                        pass  # Message might already be deleted
                    finally:
                        del self.messages[chat_id][message_id]
            if not self.messages[chat_id]:
                del self.messages[chat_id]

message_tracker = MessageTracker()

async def cleanup_job(context: ContextTypes.DEFAULT_TYPE):
    await message_tracker.cleanup_messages(context)

async def delete_message_later(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int):
    await message_tracker.add_message(chat_id, message_id)

async def send_with_warning(message, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None, parse_mode=None):
    try:
        if hasattr(message, 'reply_text'):
            sent_message = await message.reply_text(
                f"{text}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await message.edit_text(
                f"{text}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

        await delete_message_later(context, sent_message.chat_id, sent_message.message_id)
        return sent_message
    except TelegramError as e:
        print(f"Error sending message: {e}")
        return None

async def send_photo_with_warning(message, context: ContextTypes.DEFAULT_TYPE, photo: str, caption: str, reply_markup=None, parse_mode=None):
    try:
        if hasattr(message, 'reply_photo'):
            sent_message = await message.reply_photo(
                photo=photo,
                caption=f"{caption}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await context.bot.send_photo(
                chat_id=message.chat_id,
                photo=photo,
                caption=f"{caption}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

        await delete_message_later(context, sent_message.chat_id, sent_message.message_id)
        return sent_message
    except TelegramError as e:
        print(f"Error sending photo: {e}")
        return None


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    keyboard = [
        [InlineKeyboardButton("  DOWNLOAD MOVIES", callback_data='search_movies')],
        [
            InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
            InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
            InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
        ],
        [InlineKeyboardButton("📈 Popular Movies", callback_data='popular'),
         InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
        [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
        [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_with_warning(
        update.message,
        context,
        f"👋 Hello {user_name}! Welcome to @movieshuba11_bot!\n\nClick on /start to restart or type",
        reply_markup=reply_markup
    )

async def show_start_menu(message, context: ContextTypes.DEFAULT_TYPE):
    # Get user's name from the callback query
    user_name = message._effective_user.first_name if hasattr(message, '_effective_user') else "there"
    keyboard = [
        [InlineKeyboardButton(" Download movies", callback_data='search_movies')],
        [
            InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
            InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
            InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
        ],
        [InlineKeyboardButton("📈 Popular Movies", callback_data='popular')],
        [InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
        [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
        [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_with_warning(
        message,
        context,
        f"👋 Hello {user_name}! Welcome to moviieshubb_bot!\n\nClick on /start to restart or type",
        reply_markup=reply_markup
    )



async def get_random_movies_by_genre(message, context: ContextTypes.DEFAULT_TYPE, genre_id=None):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "sort_by": "popularity.desc",
            "page": 1
        }

        if genre_id:
            params["with_genres"] = genre_id

        response = requests.get(url, params=params)
        response.raise_for_status()
        total_pages = min(response.json().get("total_pages", 1), 500)

        random_page = random.randint(1, total_pages)
        params["page"] = random_page

        response = requests.get(url, params=params)
        response.raise_for_status()

        all_movies = response.json().get("results", [])
        random_movies = random.sample(all_movies, min(5, len(all_movies)))

        response_text = "🎲 Random Movie Suggestions:\n\n"
        keyboard = []
        for i, movie in enumerate(random_movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"
            keyboard.append([InlineKeyboardButton(f"🔍 Search {movie['title']}", callback_data=f'search_specific_{movie["id"]}')])

        keyboard.extend([
            [
                InlineKeyboardButton("👻 Horror", callback_data='random_horror'),
                InlineKeyboardButton("🔪 Crime", callback_data='random_crime'),
                InlineKeyboardButton("💝 Romance", callback_data='random_romance')
            ],
            [InlineKeyboardButton("🎲 More Random", callback_data='random_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching random movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='random_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                                "Sorry, couldn't fetch random movies right now.",
                                reply_markup=reply_markup)


async def get_popular_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/movie/popular"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "🎬 Currently Popular Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching popular movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='popular')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch popular movies right now.",
                              reply_markup=reply_markup)

async def get_horror_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "with_genres": HORROR_GENRE_ID,
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "👻 Popular Horror Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton("👻 More Horror Movies", callback_data='horror_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching horror movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='horror_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch horror movies right now.",
                              reply_markup=reply_markup)

async def get_bollywood_popular_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "region": "IN",
            "with_original_language": "hi",
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "🎬  Bollywood Popular Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching Bollywood movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='bollywood_popular')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch Bollywood movies right now.",
                              reply_markup=reply_markup)


async def search_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    special_case, special_links = special_cases_manager.is_special_case(query)
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Log the search
    search_logger.log_search(user_id, user_name, "movie", query)
    try:
        tmdb_handler = TMDBAPIHandler(TMDB_API_KEY)

        # Search for movie
        results = tmdb_handler.make_request(
            "/search/movie",
            params={"query": query, "language": "en-US"}
        ).get("results", [])

        if results:
            movie = results[0]
            movie_id = movie["id"]

            # Get movie details
            movie_details = tmdb_handler.make_request(f"/movie/{movie_id}")
            providers = tmdb_handler.make_request(f"/movie/{movie_id}/watch/providers").get("results", {}).get("US",
                                                                                                               {}).get(
                "flatrate", [])

        search_url = f"{TMDB_BASE_URL}/search/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        if results:
            movie = results[0]
            movie_id = movie["id"]

            details_url = f"{TMDB_BASE_URL}/movie/{movie_id}"
            watch_providers_url = f"{TMDB_BASE_URL}/movie/{movie_id}/watch/providers"

            details_response = requests.get(details_url, params={"api_key": TMDB_API_KEY})
            providers_response = requests.get(watch_providers_url, params={"api_key": TMDB_API_KEY})

            movie_details = details_response.json()
            providers = providers_response.json().get("results", {}).get("US", {}).get("flatrate", [])

            keyboard = [
                [InlineKeyboardButton(" Search Another Movie", callback_data='search_movies')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            response_text = (
                f"*{movie_details['title']}* ({movie_details.get('release_date', '')[:4]})\n\n"
                f"Plot: {movie_details.get('overview', 'No plot available')}\n\n"
            )

            if providers:
                response_text += "Available on: " + ", ".join(p["provider_name"] for p in providers) + "\n\n"
            else:
                response_text += "Streaming information not available\n\n"

            if special_case and special_links:
                response_text += "Download Links:\n"
                for link in special_links:
                    lang_text = f" ({link['language']})" if link.get('language') else ""
                    response_text += f"• {link['url']}{lang_text}\n"
            else:
                response_text += "download link comming soon msg @balaram129"

            if movie_details.get("poster_path"):
                poster_url = f"{TMDB_IMAGE_BASE_URL}{movie_details['poster_path']}"
                await send_photo_with_warning(update.message, context, photo=poster_url, caption=response_text, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                await send_with_warning(update.message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            keyboard = [
                [InlineKeyboardButton(" Try Again", callback_data='search_movies')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(update.message, context, "No movies found matching your search.", reply_markup=reply_markup)
    except Exception as e:
        print(f"Error in movie search: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(update.message, context,
                              "Sorry, there was an error processing your request. Please try again.",
                              reply_markup=reply_markup)

async def search_by_actor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Log the search
    search_logger.log_search(user_id, user_name, "actor", query)
    try:
        search_url = f"{TMDB_BASE_URL}/search/person"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        if results:
            actor = results[0]
            actor_id = actor["id"]

            actor_details_url = f"{TMDB_BASE_URL}/person/{actor_id}"
            movies_url = f"{TMDB_BASE_URL}/person/{actor_id}/movie_credits"

            actor_details_response = requests.get(actor_details_url, params={"api_key": TMDB_API_KEY})
            movies_response = requests.get(movies_url, params={"api_key": TMDB_API_KEY})

            actor_details = actor_details_response.json()
            movies = movies_response.json().get("cast", [])

            movies_with_rating = [m for m in movies if m.get("vote_average", 0) > 0]
            sorted_movies = sorted(movies_with_rating, key=lambda x: x.get("vote_average", 0), reverse=True)

            popular_movies = [m for m in sorted_movies if m.get("vote_average", 0) >= 7][:4]
            unpopular_movies = [m for m in sorted_movies if m.get("vote_average", 0) < 7][:4]

            response_text = f"🎭 {actor['name']}\n"
            if actor_details.get("birthday"):
                response_text += f"Birthday: {actor_details['birthday']}\n"
            if actor_details.get("place_of_birth"):
                response_text += f"Birthplace: {actor_details['place_of_birth']}\n"

            response_text += "\n📈 Highly Rated Movies:\n"
            for i, movie in enumerate(popular_movies, 1):
                response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
                response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"

            response_text += "\n📉 Other Notable Movies:\n"
            for i, movie in enumerate(unpopular_movies, 1):
                response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
                response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"

            keyboard = [
                [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
                [InlineKeyboardButton(" Search Another Actor", callback_data='search_actor')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            if actor.get("profile_path"):
                actor_image_url = f"{TMDB_IMAGE_BASE_URL}{actor['profile_path']}"
                await send_photo_with_warning(
                    update.message,
                    context,
                    photo=actor_image_url,
                    caption=response_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await send_with_warning(
                    update.message,
                    context,
                    response_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
        else:
            keyboard = [
                [InlineKeyboardButton(" Try Again", callback_data='search_actor')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                update.message,
                context,
                "No actor found matching your search.",
                reply_markup=reply_markup
            )
    except Exception as e:
        print(f"Error in actor search: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='search_actor')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(
            update.message,
            context,
            "Sorry, there was an error processing your request. Please try again.",
            reply_markup=reply_markup
        )
def is_special_case(query):
    query_lower = query.lower().strip()
    for key, case in special_cases_manager.items():
        if query_lower == key.lower() or query_lower in [v.lower() for v in case["variants"]]:
            return True, case["links"]
    return False, []

async def get_genre_movies(message, context: ContextTypes.DEFAULT_TYPE, genre_id: int, genre_name: str):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "with_genres": genre_id,
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = f"🎬 Popular {genre_name} Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching {genre_name} movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data=f'genre_{genre_name.lower()}')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              f"Sorry, couldn't fetch {genre_name} movies right now.",
                              reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_name = query.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    try:
        if query.data.startswith('search_specific_'):
            movie_id = query.data.split('_')[2]
            # Get movie details from TMDB
            url = f"{TMDB_BASE_URL}/movie/{movie_id}"
            response = requests.get(url, params={"api_key": TMDB_API_KEY})
            movie = response.json()

            # Create a message with movie details
            movie_text = f"{movie['title']} ({movie.get('release_date', '')[:4]})"

            # Send a temporary message to user's private chat
            class SimulatedMessage:
                def __init__(self, chat_id, text, from_user):
                    self.chat_id = chat_id
                    self.text = text
                    self.from_user = from_user

                def reply_text(self, *args, **kwargs):
                    return query.message.reply_text(*args, **kwargs)

                def reply_photo(self, *args, **kwargs):
                    return query.message.reply_photo(*args, **kwargs)

            # Create a proper message object
            simulated_message = SimulatedMessage(
                chat_id=query.message.chat_id,
                text=movie['title'],
                from_user=query.from_user
            )

            # Create a proper update object
            class SimulatedUpdate:
                def __init__(self, message):
                    self.message = message

            simulated_update = SimulatedUpdate(simulated_message)

            # Perform the search
            await search_movie(simulated_update, context)
            return
        if query.data == 'genre_horror':
            await get_genre_movies(query.message, context, GENRE_IDS['horror'], "Horror")
        elif query.data == 'genre_romance':
            await get_genre_movies(query.message, context, GENRE_IDS['romance'], "Romance")
        elif query.data == 'genre_crime':
            await get_genre_movies(query.message, context, GENRE_IDS['crime'], "Crime")
        elif query.data == 'random_movies':
            await get_random_movies_by_genre(query.message, context)
        if query.data == 'random_movies':
            await get_random_movies_by_genre(query.message, context)
        elif query.data == 'random_horror':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['horror'])
        elif query.data == 'random_crime':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['crime'])
        elif query.data == 'random_romance':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['romance'])
        elif query.data == 'horror_movies':
            await get_horror_movies(query.message, context)
        elif query.data == 'search_movies':
            USER_CONTEXT[query.message.chat_id] = 'movie'
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "🔍 Just type the name of any movie you want to search for!",
                reply_markup=reply_markup
            )
        elif query.data == 'search_actor':
            USER_CONTEXT[query.message.chat_id] = 'actor'
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "🎭 Just type the name of any actor to see their movies!",
                reply_markup=reply_markup
            )
        elif query.data == 'help':
            help_text = ("📖 How to use this bot:\n\n"
                        "1. Simply type any movie name\n"
                        "2. Or type any actor name to find their movies\n"
                        "3. I'll show you the details\n"
                        "4. Check out popular movies in both Hollywood and Bollywood\n"
                        "5. Try our random movie suggestions by genre!\n"
                        "Need more help? Just type /start to see the main menu again! or msg @balaram129")
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                help_text,
                reply_markup=reply_markup
            )
        elif query.data == 'popular':
            await get_popular_movies(query.message, context)
        elif query.data == 'bollywood_popular':
            await get_bollywood_popular_movies(query.message, context)
        elif query.data == 'start_menu':
            keyboard = [
                [InlineKeyboardButton("🔍 Download movies", callback_data='search_movies'),
                 InlineKeyboardButton("👻 Horror Movies", callback_data='horror_movies')],
                [
                    InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
                    InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
                    InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
                ],
                [InlineKeyboardButton("📈 Popular Movies", callback_data='popular')],
                [InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
                [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
                [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
                [InlineKeyboardButton("❓ Help", callback_data='help')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "👋 Welcome to moviieshubb_bot!\n\nClick on /start to restart or type",
                reply_markup=reply_markup
            )

    except Exception as e:
        print(f"Error in button callback: {e}")
        keyboard = [
            [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(
            query.message,
            context,
            "Sorry, there was an error processing your request. Please try again.",
            reply_markup=reply_markup
        )

async def handle_user_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_context = USER_CONTEXT.get(update.message.chat_id, "movie")
    if user_context == "actor":
        await search_by_actor(update, context)
    else:
        await search_movie(update, context)

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_message_later(context, update.message.chat_id, update.message.message_id)
    await handle_user_query(update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Exception while handling an update: {context.error}")
    if isinstance(context.error, Conflict):
        print("Bot instance already running. Exiting...")
        sys.exit(1)
    elif isinstance(context.error, NetworkError):
        print("Network error occurred. Waiting before retry...")
        await asyncio.sleep(1)
    else:
        print(f"Unexpected error: {context.error}")


def main():
    try:
        application = (
            Application.builder()
            .token(TELEGRAM_TOKEN)
            .build()
        )

        # Add existing handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CallbackQueryHandler(button_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))
        application.add_handler(CommandHandler("viewsearches", view_searches_command))

        # Add error handler
        application.add_error_handler(error_handler)

        # Set up the cleanup job to run every 10 seconds
        job_queue = application.job_queue
        job_queue.run_repeating(cleanup_job, interval=10, first=0)

        # Add the inactive user check job (runs every 6 hours)
        job_queue.run_repeating(check_inactive_users, interval=21600, first=21600)

        # Update stastics more frequently (every 5 minutes)
        job_queue.run_repeating(update_stastics_job, interval=300, first=0)

        # Initial statistics update
        print("Performing initial statistics update...")
        stats = SearchStatistics()
        stats.update_stastics_file()
        print("Initial statistics update completed")

        # Start the bot
        print("Starting bot...")
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

    except Exception as e:
        print(f"Error starting bot: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

# Test the logger
logger = SearchLogger()
logger.log_search(123456, "TestUser", "movie", "Avatar")

# Check recent searches
recent = logger.get_recent_searches()
print("Recent searches:", recent)import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import Conflict, NetworkError, TelegramError
import nest_asyncio
import sys
import random
from typing import Optional, Dict
from datetime import datetime, timedelta
import pickle
from special_cases_managerss import SpecialCasesManager
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import json
from datetime import datetime
from pathlib import Path


class SearchLogger:
    def __init__(self, log_file="search_logs.json"):
        self.log_file = log_file
        self.ensure_log_file_exists()

    def ensure_log_file_exists(self):
        # Create the file with an empty list if it doesn't exist or is empty
        if not Path(self.log_file).exists() or Path(self.log_file).stat().st_size == 0:
            with open(self.log_file, 'w') as f:
                json.dump([], f)

    def log_search(self, user_id: int, user_name: str, search_type: str, search_query: str):
        try:
            # First ensure the file exists and has valid JSON
            self.ensure_log_file_exists()

            # Read existing logs
            try:
                with open(self.log_file, 'r') as f:
                    logs = json.load(f)
            except json.JSONDecodeError:
                # If there's an error reading the JSON, start with an empty list
                logs = []

            # Create new log entry
            log_entry = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "user_id": user_id,
                "user_name": user_name,
                "search_type": search_type,
                "search_query": search_query
            }

            # Add new entry
            logs.append(log_entry)

            # Write back to file
            with open(self.log_file, 'w') as f:
                json.dump(logs, f, indent=2)

        except Exception as e:
            print(f"Error logging search: {e}")

    def get_recent_searches(self, limit: int = 100):
        try:
            # First ensure the file exists and has valid JSON
            self.ensure_log_file_exists()

            with open(self.log_file, 'r') as f:
                try:
                    logs = json.load(f)
                except json.JSONDecodeError:
                    return []
            return logs[-limit:]
        except Exception as e:
            print(f"Error getting recent searches: {e}")
            return []


# Create an instance of the logger
search_logger = SearchLogger()


# After your other global variables
special_cases_manager = SpecialCasesManager()

# Initialize some cases if you want (optional)
special_cases_manager.add_case(
    "pushpa 2",
    ["pushpa2", "pushpa-2", "pushpa2therule", "pushpa 2 the rule"],
    [
        {"url": "https://example4.com", "language": "Hindi"},
        {"url": "https://example5.com", "language": "Telugu"}
    ]
)

special_cases_manager.add_case(
    "venom",
    ["venom", "venom1", "venom2"],
    [
        {"url": "https://www.udlinks.com/3I1l", "language": "hindi"}
    ]
)




nest_asyncio.apply()

TELEGRAM_TOKEN = "7883754025:AAHUDU-_EM4QYome14k_28PQbPTWsl_9w6s"
TMDB_API_KEY = "c3b8704a4df65146c194940351efa9a2"
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
DELETE_TIMEOUT = 420  # 7 minutes in seconds
DISCLAIMER = "⚠️ This message will be deleted in 7 minutes"
HORROR_GENRE_ID = 27  # TMDB's genre ID for horror movies



USER_CONTEXT = {}

GENRE_IDS = {
    'horror': 27,
    'crime': 80,
    'romance': 10749
}


class TMDBAPIHandler:
    def __init__(self, api_key, base_url="https://api.themoviedb.org/3"):
        self.api_key = api_key
        self.base_url = base_url
        self.session = self._create_session()

    def _create_session(self):
        session = requests.Session()

        # Configure retry strategy
        retries = Retry(
            total=5,  # Total number of retries
            backoff_factor=0.5,  # Wait 0.5, 1, 2, 4, 8 seconds between retries
            status_forcelist=[500, 502, 503, 504, 408, 429]  # HTTP status codes to retry on
        )

        # Add retry adapter to session
        adapter = HTTPAdapter(max_retries=retries)
        session.mount('http://', adapter)
        session.mount('https://', adapter)

        return session

    def make_request(self, endpoint, params=None):
        if params is None:
            params = {}

        # Always include API key
        params['api_key'] = self.api_key

        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                response = self.session.get(
                    f"{self.base_url}{endpoint}",
                    params=params,
                    timeout=10  # 10 seconds timeout
                )
                response.raise_for_status()
                return response.json()

            except requests.exceptions.ConnectionError as e:
                if attempt == max_attempts - 1:
                    raise Exception("Unable to connect to TMDB API. Please check your internet connection.") from e
                time.sleep(2 ** attempt)  # Exponential backoff

            except requests.exceptions.Timeout as e:
                if attempt == max_attempts - 1:
                    raise Exception("TMDB API request timed out. Please try again later.") from e
                time.sleep(2 ** attempt)

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:  # Rate limit exceeded
                    retry_after = int(e.response.headers.get('Retry-After', 5))
                    time.sleep(retry_after)
                    continue
                raise Exception(f"TMDB API error: {e.response.status_code}") from e


LAST_ACTIVITY_FILE = "user_activity.pkl"
INACTIVITY_THRESHOLD = timedelta(hours=78)


class SearchStatistics:
    def __init__(self, log_file="search_logs.json", stats_file="stastics.txt"):
        self.log_file = log_file
        self.stats_file = stats_file
        self.search_logger = SearchLogger(log_file)
        # Ensure stastics file exists
        self.update_stastics_file()
        print(f"SearchStatistics initialized. Stats file: {stats_file}")

    def _load_searches(self):
        """Load searches from the log file"""
        try:
            with open(self.log_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def get_most_searched(self, days=None):
        """Get most searched queries within specified days"""
        searches = self._load_searches()
        if not searches:
            return []

        # Filter by date if days is specified
        if days:
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            searches = [s for s in searches if s['timestamp'][:10] >= cutoff_date]

        # Count search queries
        query_counts = {}
        for search in searches:
            query = search['search_query'].lower()
            query_counts[query] = query_counts.get(query, 0) + 1

        # Sort by count and return top 10
        return sorted(query_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    def get_user_search_history(self, limit=50):
        """Get recent user search history"""
        searches = self._load_searches()
        return searches[-limit:] if searches else []

    def update_stastics_file(self):  # Changed method name to match file name
        try:
            print(f"Updating stastics file at {datetime.now()}")

            # Check if log file exists and has data
            if not Path(self.log_file).exists():
                print(f"Log file {self.log_file} does not exist!")
                return

            # Load searches
            searches = self._load_searches()
            if not searches:
                print("No search data found in logs")
                stats_text = "No search data available yet.\nLast Updated: " + datetime.now().strftime(
                    '%Y-%m-%d %H:%M:%S')
            else:
                # Get statistics for different time periods
                all_time = self.get_most_searched()
                today = self.get_most_searched(days=1)
                week = self.get_most_searched(days=7)
                year = self.get_most_searched(days=365)
                user_history = self.get_user_search_history(limit=50)

                stats_text = self._format_stastics(all_time, today, week, year, user_history)  # Changed method name

            # Write to stastics file
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                f.write(stats_text)

            print(f"Stastics file updated successfully at {datetime.now()}")

            # Debug: Read and print file contents
            with open(self.stats_file, 'r', encoding='utf-8') as f:
                content = f.read()
            print(f"Stastics file size: {len(content)} bytes")

        except Exception as e:
            print(f"Error updating stastics file: {e}")
            import traceback
            traceback.print_exc()

    def _format_stastics(self, all_time, today, week, year, user_history):  # Changed method name
        stats_text = "Movie Search Stastics\n"  # Changed heading
        stats_text += "=" * 50 + "\n\n"

        # Add section for each time period
        sections = [
            ("All-Time Most Searched Movies:", all_time),
            ("Today's Most Searched Movies:", today),
            ("This Week's Most Searched Movies:", week),
            ("This Year's Most Searched Movies:", year)
        ]

        for title, data in sections:
            stats_text += f"{title}\n"
            if data:
                stats_text += "\n".join(f"{i + 1}. {movie} ({count} searches)"
                                      for i, (movie, count) in enumerate(data))
            else:
                stats_text += "No searches in this period"
            stats_text += "\n\n"

        # Add user history section
        stats_text += "Recent User Search History:\n"
        stats_text += "=" * 50 + "\n"
        if user_history:
            for search in user_history:
                stats_text += f"\nTime: {search['timestamp']}\n"
                stats_text += f"User: {search['user_name']} (ID: {search['user_id']})\n"
                stats_text += f"Search Type: {search['search_type']}\n"
                stats_text += f"Query: {search['search_query']}\n"
                stats_text += "-" * 30 + "\n"
        else:
            stats_text += "\nNo user search history available yet\n"

        stats_text += f"\nLast Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        return stats_text

# Modify the update_statistics_job to include error handling and logging
async def update_stastics_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        print(f"Starting stastics update job at {datetime.now()}")
        stats = SearchStatistics()
        stats.update_stastics_file()
        print(f"Completed stastics update job at {datetime.now()}")
    except Exception as e:
        print(f"Error in stastics update job: {e}")
        import traceback
        traceback.print_exc()

async def view_searches_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only allow yourself to see the searches
    if update.message.from_user.id == 6822829183:  # Replace with your Telegram ID
        recent_searches = search_logger.get_recent_searches(limit=10)  # Get last 10 searches

        message = "Recent Searches:\n\n"
        for search in recent_searches:
            message += f"👤 User: {search['user_name']}\n"
            message += f"🔍 Query: {search['search_query']}\n"
            message += f"⏰ Time: {search['timestamp']}\n"
            message += f"Type: {search['search_type']}\n\n"

        await update.message.reply_text(message)
    else:
        await update.message.reply_text("You don't have permission to use this command.")


# Add this to your command handlers

class UserActivityManager:
    def __init__(self):
        self.user_activity = {}
        self.load_activity()

    def load_activity(self):
        if Path(LAST_ACTIVITY_FILE).exists():
            try:
                with open(LAST_ACTIVITY_FILE, 'rb') as f:
                    self.user_activity = pickle.load(f)
            except Exception as e:
                print(f"Error loading user activity: {e}")
                self.user_activity = {}

    def save_activity(self):
        try:
            with open(LAST_ACTIVITY_FILE, 'wb') as f:
                pickle.dump(self.user_activity, f)
        except Exception as e:
            print(f"Error saving user activity: {e}")

    def update_user_activity(self, user_id: int, user_name: str):
        self.user_activity[user_id] = {
            'last_active': datetime.now(),
            'name': user_name
        }
        self.save_activity()

    def get_inactive_users(self):
        current_time = datetime.now()
        inactive_users = []

        for user_id, data in self.user_activity.items():
            if (current_time - data['last_active']) >= INACTIVITY_THRESHOLD:
                inactive_users.append({
                    'user_id': user_id,
                    'name': data['name'],
                    'last_active': data['last_active']
                })

        return inactive_users


# Create global instance
activity_manager = UserActivityManager()


# Modify the handle_user_message function to track activity
async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    await delete_message_later(context, update.message.chat_id, update.message.message_id)
    await handle_user_query(update, context)


# Add a new function to check for inactive users
async def check_inactive_users(context: ContextTypes.DEFAULT_TYPE):
    inactive_users = activity_manager.get_inactive_users()

    for user in inactive_users:
        try:
            message = f"Hey {user['name']} 👋,\n\nI am missing you dear! 💫\nIt's been a while since we last chatted. Come back and discover some amazing movies! 🎬"

            await context.bot.send_message(
                chat_id=user['user_id'],
                text=message,
                parse_mode='Markdown'
            )

            # Update the last activity to prevent spam
            activity_manager.update_user_activity(user['user_id'], user['name'])

        except Exception as e:
            print(f"Error sending reminder to user {user['user_id']}: {e}")

class MessageTracker:
    def __init__(self):
        self.messages: Dict[int, Dict[int, datetime]] = {}

    async def add_message(self, chat_id: int, message_id: int):
        if chat_id not in self.messages:
            self.messages[chat_id] = {}
        self.messages[chat_id][message_id] = datetime.now() + timedelta(seconds=DELETE_TIMEOUT)

    async def cleanup_messages(self, context: ContextTypes.DEFAULT_TYPE):
        current_time = datetime.now()
        for chat_id in list(self.messages.keys()):
            for message_id, expiry_time in list(self.messages[chat_id].items()):
                if current_time >= expiry_time:
                    try:
                        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                    except TelegramError:
                        pass  # Message might already be deleted
                    finally:
                        del self.messages[chat_id][message_id]
            if not self.messages[chat_id]:
                del self.messages[chat_id]

message_tracker = MessageTracker()

async def cleanup_job(context: ContextTypes.DEFAULT_TYPE):
    await message_tracker.cleanup_messages(context)

async def delete_message_later(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int):
    await message_tracker.add_message(chat_id, message_id)

async def send_with_warning(message, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None, parse_mode=None):
    try:
        if hasattr(message, 'reply_text'):
            sent_message = await message.reply_text(
                f"{text}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await message.edit_text(
                f"{text}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

        await delete_message_later(context, sent_message.chat_id, sent_message.message_id)
        return sent_message
    except TelegramError as e:
        print(f"Error sending message: {e}")
        return None

async def send_photo_with_warning(message, context: ContextTypes.DEFAULT_TYPE, photo: str, caption: str, reply_markup=None, parse_mode=None):
    try:
        if hasattr(message, 'reply_photo'):
            sent_message = await message.reply_photo(
                photo=photo,
                caption=f"{caption}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await context.bot.send_photo(
                chat_id=message.chat_id,
                photo=photo,
                caption=f"{caption}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

        await delete_message_later(context, sent_message.chat_id, sent_message.message_id)
        return sent_message
    except TelegramError as e:
        print(f"Error sending photo: {e}")
        return None


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    keyboard = [
        [InlineKeyboardButton("  DOWNLOAD MOVIES", callback_data='search_movies')],
        [
            InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
            InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
            InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
        ],
        [InlineKeyboardButton("📈 Popular Movies", callback_data='popular'),
         InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
        [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
        [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_with_warning(
        update.message,
        context,
        f"👋 Hello {user_name}! Welcome to @movieshuba11_bot!\n\nClick on /start to restart or type",
        reply_markup=reply_markup
    )

async def show_start_menu(message, context: ContextTypes.DEFAULT_TYPE):
    # Get user's name from the callback query
    user_name = message._effective_user.first_name if hasattr(message, '_effective_user') else "there"
    keyboard = [
        [InlineKeyboardButton(" Download movies", callback_data='search_movies')],
        [
            InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
            InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
            InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
        ],
        [InlineKeyboardButton("📈 Popular Movies", callback_data='popular')],
        [InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
        [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
        [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_with_warning(
        message,
        context,
        f"👋 Hello {user_name}! Welcome to moviieshubb_bot!\n\nClick on /start to restart or type",
        reply_markup=reply_markup
    )



async def get_random_movies_by_genre(message, context: ContextTypes.DEFAULT_TYPE, genre_id=None):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "sort_by": "popularity.desc",
            "page": 1
        }

        if genre_id:
            params["with_genres"] = genre_id

        response = requests.get(url, params=params)
        response.raise_for_status()
        total_pages = min(response.json().get("total_pages", 1), 500)

        random_page = random.randint(1, total_pages)
        params["page"] = random_page

        response = requests.get(url, params=params)
        response.raise_for_status()

        all_movies = response.json().get("results", [])
        random_movies = random.sample(all_movies, min(5, len(all_movies)))

        response_text = "🎲 Random Movie Suggestions:\n\n"
        keyboard = []
        for i, movie in enumerate(random_movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"
            keyboard.append([InlineKeyboardButton(f"🔍 Search {movie['title']}", callback_data=f'search_specific_{movie["id"]}')])

        keyboard.extend([
            [
                InlineKeyboardButton("👻 Horror", callback_data='random_horror'),
                InlineKeyboardButton("🔪 Crime", callback_data='random_crime'),
                InlineKeyboardButton("💝 Romance", callback_data='random_romance')
            ],
            [InlineKeyboardButton("🎲 More Random", callback_data='random_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching random movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='random_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                                "Sorry, couldn't fetch random movies right now.",
                                reply_markup=reply_markup)


async def get_popular_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/movie/popular"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "🎬 Currently Popular Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching popular movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='popular')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch popular movies right now.",
                              reply_markup=reply_markup)

async def get_horror_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "with_genres": HORROR_GENRE_ID,
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "👻 Popular Horror Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton("👻 More Horror Movies", callback_data='horror_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching horror movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='horror_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch horror movies right now.",
                              reply_markup=reply_markup)

async def get_bollywood_popular_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "region": "IN",
            "with_original_language": "hi",
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "🎬  Bollywood Popular Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching Bollywood movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='bollywood_popular')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch Bollywood movies right now.",
                              reply_markup=reply_markup)


async def search_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    special_case, special_links = special_cases_manager.is_special_case(query)
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Log the search
    search_logger.log_search(user_id, user_name, "movie", query)
    try:
        tmdb_handler = TMDBAPIHandler(TMDB_API_KEY)

        # Search for movie
        results = tmdb_handler.make_request(
            "/search/movie",
            params={"query": query, "language": "en-US"}
        ).get("results", [])

        if results:
            movie = results[0]
            movie_id = movie["id"]

            # Get movie details
            movie_details = tmdb_handler.make_request(f"/movie/{movie_id}")
            providers = tmdb_handler.make_request(f"/movie/{movie_id}/watch/providers").get("results", {}).get("US",
                                                                                                               {}).get(
                "flatrate", [])

        search_url = f"{TMDB_BASE_URL}/search/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        if results:
            movie = results[0]
            movie_id = movie["id"]

            details_url = f"{TMDB_BASE_URL}/movie/{movie_id}"
            watch_providers_url = f"{TMDB_BASE_URL}/movie/{movie_id}/watch/providers"

            details_response = requests.get(details_url, params={"api_key": TMDB_API_KEY})
            providers_response = requests.get(watch_providers_url, params={"api_key": TMDB_API_KEY})

            movie_details = details_response.json()
            providers = providers_response.json().get("results", {}).get("US", {}).get("flatrate", [])

            keyboard = [
                [InlineKeyboardButton(" Search Another Movie", callback_data='search_movies')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            response_text = (
                f"*{movie_details['title']}* ({movie_details.get('release_date', '')[:4]})\n\n"
                f"Plot: {movie_details.get('overview', 'No plot available')}\n\n"
            )

            if providers:
                response_text += "Available on: " + ", ".join(p["provider_name"] for p in providers) + "\n\n"
            else:
                response_text += "Streaming information not available\n\n"

            if special_case and special_links:
                response_text += "Download Links:\n"
                for link in special_links:
                    lang_text = f" ({link['language']})" if link.get('language') else ""
                    response_text += f"• {link['url']}{lang_text}\n"
            else:
                response_text += "download link comming soon msg @balaram129"

            if movie_details.get("poster_path"):
                poster_url = f"{TMDB_IMAGE_BASE_URL}{movie_details['poster_path']}"
                await send_photo_with_warning(update.message, context, photo=poster_url, caption=response_text, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                await send_with_warning(update.message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            keyboard = [
                [InlineKeyboardButton(" Try Again", callback_data='search_movies')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(update.message, context, "No movies found matching your search.", reply_markup=reply_markup)
    except Exception as e:
        print(f"Error in movie search: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(update.message, context,
                              "Sorry, there was an error processing your request. Please try again.",
                              reply_markup=reply_markup)

async def search_by_actor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Log the search
    search_logger.log_search(user_id, user_name, "actor", query)
    try:
        search_url = f"{TMDB_BASE_URL}/search/person"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        if results:
            actor = results[0]
            actor_id = actor["id"]

            actor_details_url = f"{TMDB_BASE_URL}/person/{actor_id}"
            movies_url = f"{TMDB_BASE_URL}/person/{actor_id}/movie_credits"

            actor_details_response = requests.get(actor_details_url, params={"api_key": TMDB_API_KEY})
            movies_response = requests.get(movies_url, params={"api_key": TMDB_API_KEY})

            actor_details = actor_details_response.json()
            movies = movies_response.json().get("cast", [])

            movies_with_rating = [m for m in movies if m.get("vote_average", 0) > 0]
            sorted_movies = sorted(movies_with_rating, key=lambda x: x.get("vote_average", 0), reverse=True)

            popular_movies = [m for m in sorted_movies if m.get("vote_average", 0) >= 7][:4]
            unpopular_movies = [m for m in sorted_movies if m.get("vote_average", 0) < 7][:4]

            response_text = f"🎭 {actor['name']}\n"
            if actor_details.get("birthday"):
                response_text += f"Birthday: {actor_details['birthday']}\n"
            if actor_details.get("place_of_birth"):
                response_text += f"Birthplace: {actor_details['place_of_birth']}\n"

            response_text += "\n📈 Highly Rated Movies:\n"
            for i, movie in enumerate(popular_movies, 1):
                response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
                response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"

            response_text += "\n📉 Other Notable Movies:\n"
            for i, movie in enumerate(unpopular_movies, 1):
                response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
                response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"

            keyboard = [
                [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
                [InlineKeyboardButton(" Search Another Actor", callback_data='search_actor')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            if actor.get("profile_path"):
                actor_image_url = f"{TMDB_IMAGE_BASE_URL}{actor['profile_path']}"
                await send_photo_with_warning(
                    update.message,
                    context,
                    photo=actor_image_url,
                    caption=response_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await send_with_warning(
                    update.message,
                    context,
                    response_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
        else:
            keyboard = [
                [InlineKeyboardButton(" Try Again", callback_data='search_actor')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                update.message,
                context,
                "No actor found matching your search.",
                reply_markup=reply_markup
            )
    except Exception as e:
        print(f"Error in actor search: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='search_actor')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(
            update.message,
            context,
            "Sorry, there was an error processing your request. Please try again.",
            reply_markup=reply_markup
        )
def is_special_case(query):
    query_lower = query.lower().strip()
    for key, case in special_cases_manager.items():
        if query_lower == key.lower() or query_lower in [v.lower() for v in case["variants"]]:
            return True, case["links"]
    return False, []

async def get_genre_movies(message, context: ContextTypes.DEFAULT_TYPE, genre_id: int, genre_name: str):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "with_genres": genre_id,
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = f"🎬 Popular {genre_name} Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching {genre_name} movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data=f'genre_{genre_name.lower()}')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              f"Sorry, couldn't fetch {genre_name} movies right now.",
                              reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_name = query.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    try:
        if query.data.startswith('search_specific_'):
            movie_id = query.data.split('_')[2]
            # Get movie details from TMDB
            url = f"{TMDB_BASE_URL}/movie/{movie_id}"
            response = requests.get(url, params={"api_key": TMDB_API_KEY})
            movie = response.json()

            # Create a message with movie details
            movie_text = f"{movie['title']} ({movie.get('release_date', '')[:4]})"

            # Send a temporary message to user's private chat
            class SimulatedMessage:
                def __init__(self, chat_id, text, from_user):
                    self.chat_id = chat_id
                    self.text = text
                    self.from_user = from_user

                def reply_text(self, *args, **kwargs):
                    return query.message.reply_text(*args, **kwargs)

                def reply_photo(self, *args, **kwargs):
                    return query.message.reply_photo(*args, **kwargs)

            # Create a proper message object
            simulated_message = SimulatedMessage(
                chat_id=query.message.chat_id,
                text=movie['title'],
                from_user=query.from_user
            )

            # Create a proper update object
            class SimulatedUpdate:
                def __init__(self, message):
                    self.message = message

            simulated_update = SimulatedUpdate(simulated_message)

            # Perform the search
            await search_movie(simulated_update, context)
            return
        if query.data == 'genre_horror':
            await get_genre_movies(query.message, context, GENRE_IDS['horror'], "Horror")
        elif query.data == 'genre_romance':
            await get_genre_movies(query.message, context, GENRE_IDS['romance'], "Romance")
        elif query.data == 'genre_crime':
            await get_genre_movies(query.message, context, GENRE_IDS['crime'], "Crime")
        elif query.data == 'random_movies':
            await get_random_movies_by_genre(query.message, context)
        if query.data == 'random_movies':
            await get_random_movies_by_genre(query.message, context)
        elif query.data == 'random_horror':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['horror'])
        elif query.data == 'random_crime':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['crime'])
        elif query.data == 'random_romance':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['romance'])
        elif query.data == 'horror_movies':
            await get_horror_movies(query.message, context)
        elif query.data == 'search_movies':
            USER_CONTEXT[query.message.chat_id] = 'movie'
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "🔍 Just type the name of any movie you want to search for!",
                reply_markup=reply_markup
            )
        elif query.data == 'search_actor':
            USER_CONTEXT[query.message.chat_id] = 'actor'
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "🎭 Just type the name of any actor to see their movies!",
                reply_markup=reply_markup
            )
        elif query.data == 'help':
            help_text = ("📖 How to use this bot:\n\n"
                        "1. Simply type any movie name\n"
                        "2. Or type any actor name to find their movies\n"
                        "3. I'll show you the details\n"
                        "4. Check out popular movies in both Hollywood and Bollywood\n"
                        "5. Try our random movie suggestions by genre!\n"
                        "Need more help? Just type /start to see the main menu again! or msg @balaram129")
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                help_text,
                reply_markup=reply_markup
            )
        elif query.data == 'popular':
            await get_popular_movies(query.message, context)
        elif query.data == 'bollywood_popular':
            await get_bollywood_popular_movies(query.message, context)
        elif query.data == 'start_menu':
            keyboard = [
                [InlineKeyboardButton("🔍 Download movies", callback_data='search_movies'),
                 InlineKeyboardButton("👻 Horror Movies", callback_data='horror_movies')],
                [
                    InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
                    InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
                    InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
                ],
                [InlineKeyboardButton("📈 Popular Movies", callback_data='popular')],
                [InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
                [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
                [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
                [InlineKeyboardButton("❓ Help", callback_data='help')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "👋 Welcome to moviieshubb_bot!\n\nClick on /start to restart or type",
                reply_markup=reply_markup
            )

    except Exception as e:
        print(f"Error in button callback: {e}")
        keyboard = [
            [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(
            query.message,
            context,
            "Sorry, there was an error processing your request. Please try again.",
            reply_markup=reply_markup
        )

async def handle_user_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_context = USER_CONTEXT.get(update.message.chat_id, "movie")
    if user_context == "actor":
        await search_by_actor(update, context)
    else:
        await search_movie(update, context)

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_message_later(context, update.message.chat_id, update.message.message_id)
    await handle_user_query(update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Exception while handling an update: {context.error}")
    if isinstance(context.error, Conflict):
        print("Bot instance already running. Exiting...")
        sys.exit(1)
    elif isinstance(context.error, NetworkError):
        print("Network error occurred. Waiting before retry...")
        await asyncio.sleep(1)
    else:
        print(f"Unexpected error: {context.error}")


def main():
    try:
        application = (
            Application.builder()
            .token(TELEGRAM_TOKEN)
            .build()
        )

        # Add existing handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CallbackQueryHandler(button_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))
        application.add_handler(CommandHandler("viewsearches", view_searches_command))

        # Add error handler
        application.add_error_handler(error_handler)

        # Set up the cleanup job to run every 10 seconds
        job_queue = application.job_queue
        job_queue.run_repeating(cleanup_job, interval=10, first=0)

        # Add the inactive user check job (runs every 6 hours)
        job_queue.run_repeating(check_inactive_users, interval=21600, first=21600)

        # Update stastics more frequently (every 5 minutes)
        job_queue.run_repeating(update_stastics_job, interval=300, first=0)

        # Initial statistics update
        print("Performing initial statistics update...")
        stats = SearchStatistics()
        stats.update_stastics_file()
        print("Initial statistics update completed")

        # Start the bot
        print("Starting bot...")
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

    except Exception as e:
        print(f"Error starting bot: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

# Test the logger
logger = SearchLogger()
logger.log_search(123456, "TestUser", "movie", "Avatar")

# Check recent searches
recent = logger.get_recent_searches()
print("Recent searches:", recent)import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import Conflict, NetworkError, TelegramError
import nest_asyncio
import sys
import random
from typing import Optional, Dict
from datetime import datetime, timedelta
import pickle
from special_cases_managerss import SpecialCasesManager
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import json
from datetime import datetime
from pathlib import Path


class SearchLogger:
    def __init__(self, log_file="search_logs.json"):
        self.log_file = log_file
        self.ensure_log_file_exists()

    def ensure_log_file_exists(self):
        # Create the file with an empty list if it doesn't exist or is empty
        if not Path(self.log_file).exists() or Path(self.log_file).stat().st_size == 0:
            with open(self.log_file, 'w') as f:
                json.dump([], f)

    def log_search(self, user_id: int, user_name: str, search_type: str, search_query: str):
        try:
            # First ensure the file exists and has valid JSON
            self.ensure_log_file_exists()

            # Read existing logs
            try:
                with open(self.log_file, 'r') as f:
                    logs = json.load(f)
            except json.JSONDecodeError:
                # If there's an error reading the JSON, start with an empty list
                logs = []

            # Create new log entry
            log_entry = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "user_id": user_id,
                "user_name": user_name,
                "search_type": search_type,
                "search_query": search_query
            }

            # Add new entry
            logs.append(log_entry)

            # Write back to file
            with open(self.log_file, 'w') as f:
                json.dump(logs, f, indent=2)

        except Exception as e:
            print(f"Error logging search: {e}")

    def get_recent_searches(self, limit: int = 100):
        try:
            # First ensure the file exists and has valid JSON
            self.ensure_log_file_exists()

            with open(self.log_file, 'r') as f:
                try:
                    logs = json.load(f)
                except json.JSONDecodeError:
                    return []
            return logs[-limit:]
        except Exception as e:
            print(f"Error getting recent searches: {e}")
            return []


# Create an instance of the logger
search_logger = SearchLogger()


# After your other global variables
special_cases_manager = SpecialCasesManager()

# Initialize some cases if you want (optional)
special_cases_manager.add_case(
    "pushpa 2",
    ["pushpa2", "pushpa-2", "pushpa2therule", "pushpa 2 the rule"],
    [
        {"url": "https://example4.com", "language": "Hindi"},
        {"url": "https://example5.com", "language": "Telugu"}
    ]
)

special_cases_manager.add_case(
    "venom",
    ["venom", "venom1", "venom2"],
    [
        {"url": "https://www.udlinks.com/3I1l", "language": "hindi"}
    ]
)




nest_asyncio.apply()

TELEGRAM_TOKEN = "7883754025:AAHUDU-_EM4QYome14k_28PQbPTWsl_9w6s"
TMDB_API_KEY = "c3b8704a4df65146c194940351efa9a2"
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
DELETE_TIMEOUT = 420  # 7 minutes in seconds
DISCLAIMER = "⚠️ This message will be deleted in 7 minutes"
HORROR_GENRE_ID = 27  # TMDB's genre ID for horror movies



USER_CONTEXT = {}

GENRE_IDS = {
    'horror': 27,
    'crime': 80,
    'romance': 10749
}


class TMDBAPIHandler:
    def __init__(self, api_key, base_url="https://api.themoviedb.org/3"):
        self.api_key = api_key
        self.base_url = base_url
        self.session = self._create_session()

    def _create_session(self):
        session = requests.Session()

        # Configure retry strategy
        retries = Retry(
            total=5,  # Total number of retries
            backoff_factor=0.5,  # Wait 0.5, 1, 2, 4, 8 seconds between retries
            status_forcelist=[500, 502, 503, 504, 408, 429]  # HTTP status codes to retry on
        )

        # Add retry adapter to session
        adapter = HTTPAdapter(max_retries=retries)
        session.mount('http://', adapter)
        session.mount('https://', adapter)

        return session

    def make_request(self, endpoint, params=None):
        if params is None:
            params = {}

        # Always include API key
        params['api_key'] = self.api_key

        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                response = self.session.get(
                    f"{self.base_url}{endpoint}",
                    params=params,
                    timeout=10  # 10 seconds timeout
                )
                response.raise_for_status()
                return response.json()

            except requests.exceptions.ConnectionError as e:
                if attempt == max_attempts - 1:
                    raise Exception("Unable to connect to TMDB API. Please check your internet connection.") from e
                time.sleep(2 ** attempt)  # Exponential backoff

            except requests.exceptions.Timeout as e:
                if attempt == max_attempts - 1:
                    raise Exception("TMDB API request timed out. Please try again later.") from e
                time.sleep(2 ** attempt)

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:  # Rate limit exceeded
                    retry_after = int(e.response.headers.get('Retry-After', 5))
                    time.sleep(retry_after)
                    continue
                raise Exception(f"TMDB API error: {e.response.status_code}") from e


LAST_ACTIVITY_FILE = "user_activity.pkl"
INACTIVITY_THRESHOLD = timedelta(hours=78)


class SearchStatistics:
    def __init__(self, log_file="search_logs.json", stats_file="stastics.txt"):
        self.log_file = log_file
        self.stats_file = stats_file
        self.search_logger = SearchLogger(log_file)
        # Ensure stastics file exists
        self.update_stastics_file()
        print(f"SearchStatistics initialized. Stats file: {stats_file}")

    def _load_searches(self):
        """Load searches from the log file"""
        try:
            with open(self.log_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def get_most_searched(self, days=None):
        """Get most searched queries within specified days"""
        searches = self._load_searches()
        if not searches:
            return []

        # Filter by date if days is specified
        if days:
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            searches = [s for s in searches if s['timestamp'][:10] >= cutoff_date]

        # Count search queries
        query_counts = {}
        for search in searches:
            query = search['search_query'].lower()
            query_counts[query] = query_counts.get(query, 0) + 1

        # Sort by count and return top 10
        return sorted(query_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    def get_user_search_history(self, limit=50):
        """Get recent user search history"""
        searches = self._load_searches()
        return searches[-limit:] if searches else []

    def update_stastics_file(self):  # Changed method name to match file name
        try:
            print(f"Updating stastics file at {datetime.now()}")

            # Check if log file exists and has data
            if not Path(self.log_file).exists():
                print(f"Log file {self.log_file} does not exist!")
                return

            # Load searches
            searches = self._load_searches()
            if not searches:
                print("No search data found in logs")
                stats_text = "No search data available yet.\nLast Updated: " + datetime.now().strftime(
                    '%Y-%m-%d %H:%M:%S')
            else:
                # Get statistics for different time periods
                all_time = self.get_most_searched()
                today = self.get_most_searched(days=1)
                week = self.get_most_searched(days=7)
                year = self.get_most_searched(days=365)
                user_history = self.get_user_search_history(limit=50)

                stats_text = self._format_stastics(all_time, today, week, year, user_history)  # Changed method name

            # Write to stastics file
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                f.write(stats_text)

            print(f"Stastics file updated successfully at {datetime.now()}")

            # Debug: Read and print file contents
            with open(self.stats_file, 'r', encoding='utf-8') as f:
                content = f.read()
            print(f"Stastics file size: {len(content)} bytes")

        except Exception as e:
            print(f"Error updating stastics file: {e}")
            import traceback
            traceback.print_exc()

    def _format_stastics(self, all_time, today, week, year, user_history):  # Changed method name
        stats_text = "Movie Search Stastics\n"  # Changed heading
        stats_text += "=" * 50 + "\n\n"

        # Add section for each time period
        sections = [
            ("All-Time Most Searched Movies:", all_time),
            ("Today's Most Searched Movies:", today),
            ("This Week's Most Searched Movies:", week),
            ("This Year's Most Searched Movies:", year)
        ]

        for title, data in sections:
            stats_text += f"{title}\n"
            if data:
                stats_text += "\n".join(f"{i + 1}. {movie} ({count} searches)"
                                      for i, (movie, count) in enumerate(data))
            else:
                stats_text += "No searches in this period"
            stats_text += "\n\n"

        # Add user history section
        stats_text += "Recent User Search History:\n"
        stats_text += "=" * 50 + "\n"
        if user_history:
            for search in user_history:
                stats_text += f"\nTime: {search['timestamp']}\n"
                stats_text += f"User: {search['user_name']} (ID: {search['user_id']})\n"
                stats_text += f"Search Type: {search['search_type']}\n"
                stats_text += f"Query: {search['search_query']}\n"
                stats_text += "-" * 30 + "\n"
        else:
            stats_text += "\nNo user search history available yet\n"

        stats_text += f"\nLast Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        return stats_text

# Modify the update_statistics_job to include error handling and logging
async def update_stastics_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        print(f"Starting stastics update job at {datetime.now()}")
        stats = SearchStatistics()
        stats.update_stastics_file()
        print(f"Completed stastics update job at {datetime.now()}")
    except Exception as e:
        print(f"Error in stastics update job: {e}")
        import traceback
        traceback.print_exc()

async def view_searches_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only allow yourself to see the searches
    if update.message.from_user.id == 6822829183:  # Replace with your Telegram ID
        recent_searches = search_logger.get_recent_searches(limit=10)  # Get last 10 searches

        message = "Recent Searches:\n\n"
        for search in recent_searches:
            message += f"👤 User: {search['user_name']}\n"
            message += f"🔍 Query: {search['search_query']}\n"
            message += f"⏰ Time: {search['timestamp']}\n"
            message += f"Type: {search['search_type']}\n\n"

        await update.message.reply_text(message)
    else:
        await update.message.reply_text("You don't have permission to use this command.")


# Add this to your command handlers

class UserActivityManager:
    def __init__(self):
        self.user_activity = {}
        self.load_activity()

    def load_activity(self):
        if Path(LAST_ACTIVITY_FILE).exists():
            try:
                with open(LAST_ACTIVITY_FILE, 'rb') as f:
                    self.user_activity = pickle.load(f)
            except Exception as e:
                print(f"Error loading user activity: {e}")
                self.user_activity = {}

    def save_activity(self):
        try:
            with open(LAST_ACTIVITY_FILE, 'wb') as f:
                pickle.dump(self.user_activity, f)
        except Exception as e:
            print(f"Error saving user activity: {e}")

    def update_user_activity(self, user_id: int, user_name: str):
        self.user_activity[user_id] = {
            'last_active': datetime.now(),
            'name': user_name
        }
        self.save_activity()

    def get_inactive_users(self):
        current_time = datetime.now()
        inactive_users = []

        for user_id, data in self.user_activity.items():
            if (current_time - data['last_active']) >= INACTIVITY_THRESHOLD:
                inactive_users.append({
                    'user_id': user_id,
                    'name': data['name'],
                    'last_active': data['last_active']
                })

        return inactive_users


# Create global instance
activity_manager = UserActivityManager()


# Modify the handle_user_message function to track activity
async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    await delete_message_later(context, update.message.chat_id, update.message.message_id)
    await handle_user_query(update, context)


# Add a new function to check for inactive users
async def check_inactive_users(context: ContextTypes.DEFAULT_TYPE):
    inactive_users = activity_manager.get_inactive_users()

    for user in inactive_users:
        try:
            message = f"Hey {user['name']} 👋,\n\nI am missing you dear! 💫\nIt's been a while since we last chatted. Come back and discover some amazing movies! 🎬"

            await context.bot.send_message(
                chat_id=user['user_id'],
                text=message,
                parse_mode='Markdown'
            )

            # Update the last activity to prevent spam
            activity_manager.update_user_activity(user['user_id'], user['name'])

        except Exception as e:
            print(f"Error sending reminder to user {user['user_id']}: {e}")

class MessageTracker:
    def __init__(self):
        self.messages: Dict[int, Dict[int, datetime]] = {}

    async def add_message(self, chat_id: int, message_id: int):
        if chat_id not in self.messages:
            self.messages[chat_id] = {}
        self.messages[chat_id][message_id] = datetime.now() + timedelta(seconds=DELETE_TIMEOUT)

    async def cleanup_messages(self, context: ContextTypes.DEFAULT_TYPE):
        current_time = datetime.now()
        for chat_id in list(self.messages.keys()):
            for message_id, expiry_time in list(self.messages[chat_id].items()):
                if current_time >= expiry_time:
                    try:
                        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                    except TelegramError:
                        pass  # Message might already be deleted
                    finally:
                        del self.messages[chat_id][message_id]
            if not self.messages[chat_id]:
                del self.messages[chat_id]

message_tracker = MessageTracker()

async def cleanup_job(context: ContextTypes.DEFAULT_TYPE):
    await message_tracker.cleanup_messages(context)

async def delete_message_later(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int):
    await message_tracker.add_message(chat_id, message_id)

async def send_with_warning(message, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None, parse_mode=None):
    try:
        if hasattr(message, 'reply_text'):
            sent_message = await message.reply_text(
                f"{text}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await message.edit_text(
                f"{text}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

        await delete_message_later(context, sent_message.chat_id, sent_message.message_id)
        return sent_message
    except TelegramError as e:
        print(f"Error sending message: {e}")
        return None

async def send_photo_with_warning(message, context: ContextTypes.DEFAULT_TYPE, photo: str, caption: str, reply_markup=None, parse_mode=None):
    try:
        if hasattr(message, 'reply_photo'):
            sent_message = await message.reply_photo(
                photo=photo,
                caption=f"{caption}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await context.bot.send_photo(
                chat_id=message.chat_id,
                photo=photo,
                caption=f"{caption}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

        await delete_message_later(context, sent_message.chat_id, sent_message.message_id)
        return sent_message
    except TelegramError as e:
        print(f"Error sending photo: {e}")
        return None


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    keyboard = [
        [InlineKeyboardButton("  DOWNLOAD MOVIES", callback_data='search_movies')],
        [
            InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
            InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
            InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
        ],
        [InlineKeyboardButton("📈 Popular Movies", callback_data='popular'),
         InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
        [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
        [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_with_warning(
        update.message,
        context,
        f"👋 Hello {user_name}! Welcome to @movieshuba11_bot!\n\nClick on /start to restart or type",
        reply_markup=reply_markup
    )

async def show_start_menu(message, context: ContextTypes.DEFAULT_TYPE):
    # Get user's name from the callback query
    user_name = message._effective_user.first_name if hasattr(message, '_effective_user') else "there"
    keyboard = [
        [InlineKeyboardButton(" Download movies", callback_data='search_movies')],
        [
            InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
            InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
            InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
        ],
        [InlineKeyboardButton("📈 Popular Movies", callback_data='popular')],
        [InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
        [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
        [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_with_warning(
        message,
        context,
        f"👋 Hello {user_name}! Welcome to moviieshubb_bot!\n\nClick on /start to restart or type",
        reply_markup=reply_markup
    )



async def get_random_movies_by_genre(message, context: ContextTypes.DEFAULT_TYPE, genre_id=None):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "sort_by": "popularity.desc",
            "page": 1
        }

        if genre_id:
            params["with_genres"] = genre_id

        response = requests.get(url, params=params)
        response.raise_for_status()
        total_pages = min(response.json().get("total_pages", 1), 500)

        random_page = random.randint(1, total_pages)
        params["page"] = random_page

        response = requests.get(url, params=params)
        response.raise_for_status()

        all_movies = response.json().get("results", [])
        random_movies = random.sample(all_movies, min(5, len(all_movies)))

        response_text = "🎲 Random Movie Suggestions:\n\n"
        keyboard = []
        for i, movie in enumerate(random_movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"
            keyboard.append([InlineKeyboardButton(f"🔍 Search {movie['title']}", callback_data=f'search_specific_{movie["id"]}')])

        keyboard.extend([
            [
                InlineKeyboardButton("👻 Horror", callback_data='random_horror'),
                InlineKeyboardButton("🔪 Crime", callback_data='random_crime'),
                InlineKeyboardButton("💝 Romance", callback_data='random_romance')
            ],
            [InlineKeyboardButton("🎲 More Random", callback_data='random_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching random movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='random_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                                "Sorry, couldn't fetch random movies right now.",
                                reply_markup=reply_markup)


async def get_popular_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/movie/popular"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "🎬 Currently Popular Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching popular movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='popular')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch popular movies right now.",
                              reply_markup=reply_markup)

async def get_horror_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "with_genres": HORROR_GENRE_ID,
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "👻 Popular Horror Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton("👻 More Horror Movies", callback_data='horror_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching horror movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='horror_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch horror movies right now.",
                              reply_markup=reply_markup)

async def get_bollywood_popular_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "region": "IN",
            "with_original_language": "hi",
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "🎬  Bollywood Popular Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching Bollywood movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='bollywood_popular')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch Bollywood movies right now.",
                              reply_markup=reply_markup)


async def search_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    special_case, special_links = special_cases_manager.is_special_case(query)
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Log the search
    search_logger.log_search(user_id, user_name, "movie", query)
    try:
        tmdb_handler = TMDBAPIHandler(TMDB_API_KEY)

        # Search for movie
        results = tmdb_handler.make_request(
            "/search/movie",
            params={"query": query, "language": "en-US"}
        ).get("results", [])

        if results:
            movie = results[0]
            movie_id = movie["id"]

            # Get movie details
            movie_details = tmdb_handler.make_request(f"/movie/{movie_id}")
            providers = tmdb_handler.make_request(f"/movie/{movie_id}/watch/providers").get("results", {}).get("US",
                                                                                                               {}).get(
                "flatrate", [])

        search_url = f"{TMDB_BASE_URL}/search/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        if results:
            movie = results[0]
            movie_id = movie["id"]

            details_url = f"{TMDB_BASE_URL}/movie/{movie_id}"
            watch_providers_url = f"{TMDB_BASE_URL}/movie/{movie_id}/watch/providers"

            details_response = requests.get(details_url, params={"api_key": TMDB_API_KEY})
            providers_response = requests.get(watch_providers_url, params={"api_key": TMDB_API_KEY})

            movie_details = details_response.json()
            providers = providers_response.json().get("results", {}).get("US", {}).get("flatrate", [])

            keyboard = [
                [InlineKeyboardButton(" Search Another Movie", callback_data='search_movies')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            response_text = (
                f"*{movie_details['title']}* ({movie_details.get('release_date', '')[:4]})\n\n"
                f"Plot: {movie_details.get('overview', 'No plot available')}\n\n"
            )

            if providers:
                response_text += "Available on: " + ", ".join(p["provider_name"] for p in providers) + "\n\n"
            else:
                response_text += "Streaming information not available\n\n"

            if special_case and special_links:
                response_text += "Download Links:\n"
                for link in special_links:
                    lang_text = f" ({link['language']})" if link.get('language') else ""
                    response_text += f"• {link['url']}{lang_text}\n"
            else:
                response_text += "download link comming soon msg @balaram129"

            if movie_details.get("poster_path"):
                poster_url = f"{TMDB_IMAGE_BASE_URL}{movie_details['poster_path']}"
                await send_photo_with_warning(update.message, context, photo=poster_url, caption=response_text, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                await send_with_warning(update.message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            keyboard = [
                [InlineKeyboardButton(" Try Again", callback_data='search_movies')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(update.message, context, "No movies found matching your search.", reply_markup=reply_markup)
    except Exception as e:
        print(f"Error in movie search: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(update.message, context,
                              "Sorry, there was an error processing your request. Please try again.",
                              reply_markup=reply_markup)

async def search_by_actor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Log the search
    search_logger.log_search(user_id, user_name, "actor", query)
    try:
        search_url = f"{TMDB_BASE_URL}/search/person"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        if results:
            actor = results[0]
            actor_id = actor["id"]

            actor_details_url = f"{TMDB_BASE_URL}/person/{actor_id}"
            movies_url = f"{TMDB_BASE_URL}/person/{actor_id}/movie_credits"

            actor_details_response = requests.get(actor_details_url, params={"api_key": TMDB_API_KEY})
            movies_response = requests.get(movies_url, params={"api_key": TMDB_API_KEY})

            actor_details = actor_details_response.json()
            movies = movies_response.json().get("cast", [])

            movies_with_rating = [m for m in movies if m.get("vote_average", 0) > 0]
            sorted_movies = sorted(movies_with_rating, key=lambda x: x.get("vote_average", 0), reverse=True)

            popular_movies = [m for m in sorted_movies if m.get("vote_average", 0) >= 7][:4]
            unpopular_movies = [m for m in sorted_movies if m.get("vote_average", 0) < 7][:4]

            response_text = f"🎭 {actor['name']}\n"
            if actor_details.get("birthday"):
                response_text += f"Birthday: {actor_details['birthday']}\n"
            if actor_details.get("place_of_birth"):
                response_text += f"Birthplace: {actor_details['place_of_birth']}\n"

            response_text += "\n📈 Highly Rated Movies:\n"
            for i, movie in enumerate(popular_movies, 1):
                response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
                response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"

            response_text += "\n📉 Other Notable Movies:\n"
            for i, movie in enumerate(unpopular_movies, 1):
                response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
                response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"

            keyboard = [
                [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
                [InlineKeyboardButton(" Search Another Actor", callback_data='search_actor')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            if actor.get("profile_path"):
                actor_image_url = f"{TMDB_IMAGE_BASE_URL}{actor['profile_path']}"
                await send_photo_with_warning(
                    update.message,
                    context,
                    photo=actor_image_url,
                    caption=response_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await send_with_warning(
                    update.message,
                    context,
                    response_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
        else:
            keyboard = [
                [InlineKeyboardButton(" Try Again", callback_data='search_actor')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                update.message,
                context,
                "No actor found matching your search.",
                reply_markup=reply_markup
            )
    except Exception as e:
        print(f"Error in actor search: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='search_actor')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(
            update.message,
            context,
            "Sorry, there was an error processing your request. Please try again.",
            reply_markup=reply_markup
        )
def is_special_case(query):
    query_lower = query.lower().strip()
    for key, case in special_cases_manager.items():
        if query_lower == key.lower() or query_lower in [v.lower() for v in case["variants"]]:
            return True, case["links"]
    return False, []

async def get_genre_movies(message, context: ContextTypes.DEFAULT_TYPE, genre_id: int, genre_name: str):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "with_genres": genre_id,
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = f"🎬 Popular {genre_name} Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching {genre_name} movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data=f'genre_{genre_name.lower()}')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              f"Sorry, couldn't fetch {genre_name} movies right now.",
                              reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_name = query.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    try:
        if query.data.startswith('search_specific_'):
            movie_id = query.data.split('_')[2]
            # Get movie details from TMDB
            url = f"{TMDB_BASE_URL}/movie/{movie_id}"
            response = requests.get(url, params={"api_key": TMDB_API_KEY})
            movie = response.json()

            # Create a message with movie details
            movie_text = f"{movie['title']} ({movie.get('release_date', '')[:4]})"

            # Send a temporary message to user's private chat
            class SimulatedMessage:
                def __init__(self, chat_id, text, from_user):
                    self.chat_id = chat_id
                    self.text = text
                    self.from_user = from_user

                def reply_text(self, *args, **kwargs):
                    return query.message.reply_text(*args, **kwargs)

                def reply_photo(self, *args, **kwargs):
                    return query.message.reply_photo(*args, **kwargs)

            # Create a proper message object
            simulated_message = SimulatedMessage(
                chat_id=query.message.chat_id,
                text=movie['title'],
                from_user=query.from_user
            )

            # Create a proper update object
            class SimulatedUpdate:
                def __init__(self, message):
                    self.message = message

            simulated_update = SimulatedUpdate(simulated_message)

            # Perform the search
            await search_movie(simulated_update, context)
            return
        if query.data == 'genre_horror':
            await get_genre_movies(query.message, context, GENRE_IDS['horror'], "Horror")
        elif query.data == 'genre_romance':
            await get_genre_movies(query.message, context, GENRE_IDS['romance'], "Romance")
        elif query.data == 'genre_crime':
            await get_genre_movies(query.message, context, GENRE_IDS['crime'], "Crime")
        elif query.data == 'random_movies':
            await get_random_movies_by_genre(query.message, context)
        if query.data == 'random_movies':
            await get_random_movies_by_genre(query.message, context)
        elif query.data == 'random_horror':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['horror'])
        elif query.data == 'random_crime':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['crime'])
        elif query.data == 'random_romance':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['romance'])
        elif query.data == 'horror_movies':
            await get_horror_movies(query.message, context)
        elif query.data == 'search_movies':
            USER_CONTEXT[query.message.chat_id] = 'movie'
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "🔍 Just type the name of any movie you want to search for!",
                reply_markup=reply_markup
            )
        elif query.data == 'search_actor':
            USER_CONTEXT[query.message.chat_id] = 'actor'
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "🎭 Just type the name of any actor to see their movies!",
                reply_markup=reply_markup
            )
        elif query.data == 'help':
            help_text = ("📖 How to use this bot:\n\n"
                        "1. Simply type any movie name\n"
                        "2. Or type any actor name to find their movies\n"
                        "3. I'll show you the details\n"
                        "4. Check out popular movies in both Hollywood and Bollywood\n"
                        "5. Try our random movie suggestions by genre!\n"
                        "Need more help? Just type /start to see the main menu again! or msg @balaram129")
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                help_text,
                reply_markup=reply_markup
            )
        elif query.data == 'popular':
            await get_popular_movies(query.message, context)
        elif query.data == 'bollywood_popular':
            await get_bollywood_popular_movies(query.message, context)
        elif query.data == 'start_menu':
            keyboard = [
                [InlineKeyboardButton("🔍 Download movies", callback_data='search_movies'),
                 InlineKeyboardButton("👻 Horror Movies", callback_data='horror_movies')],
                [
                    InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
                    InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
                    InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
                ],
                [InlineKeyboardButton("📈 Popular Movies", callback_data='popular')],
                [InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
                [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
                [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
                [InlineKeyboardButton("❓ Help", callback_data='help')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "👋 Welcome to moviieshubb_bot!\n\nClick on /start to restart or type",
                reply_markup=reply_markup
            )

    except Exception as e:
        print(f"Error in button callback: {e}")
        keyboard = [
            [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(
            query.message,
            context,
            "Sorry, there was an error processing your request. Please try again.",
            reply_markup=reply_markup
        )

async def handle_user_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_context = USER_CONTEXT.get(update.message.chat_id, "movie")
    if user_context == "actor":
        await search_by_actor(update, context)
    else:
        await search_movie(update, context)

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_message_later(context, update.message.chat_id, update.message.message_id)
    await handle_user_query(update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Exception while handling an update: {context.error}")
    if isinstance(context.error, Conflict):
        print("Bot instance already running. Exiting...")
        sys.exit(1)
    elif isinstance(context.error, NetworkError):
        print("Network error occurred. Waiting before retry...")
        await asyncio.sleep(1)
    else:
        print(f"Unexpected error: {context.error}")


def main():
    try:
        application = (
            Application.builder()
            .token(TELEGRAM_TOKEN)
            .build()
        )

        # Add existing handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CallbackQueryHandler(button_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))
        application.add_handler(CommandHandler("viewsearches", view_searches_command))

        # Add error handler
        application.add_error_handler(error_handler)

        # Set up the cleanup job to run every 10 seconds
        job_queue = application.job_queue
        job_queue.run_repeating(cleanup_job, interval=10, first=0)

        # Add the inactive user check job (runs every 6 hours)
        job_queue.run_repeating(check_inactive_users, interval=21600, first=21600)

        # Update stastics more frequently (every 5 minutes)
        job_queue.run_repeating(update_stastics_job, interval=300, first=0)

        # Initial statistics update
        print("Performing initial statistics update...")
        stats = SearchStatistics()
        stats.update_stastics_file()
        print("Initial statistics update completed")

        # Start the bot
        print("Starting bot...")
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

    except Exception as e:
        print(f"Error starting bot: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

# Test the logger
logger = SearchLogger()
logger.log_search(123456, "TestUser", "movie", "Avatar")

# Check recent searches
recent = logger.get_recent_searches()
print("Recent searches:", recent)import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import Conflict, NetworkError, TelegramError
import nest_asyncio
import sys
import random
from typing import Optional, Dict
from datetime import datetime, timedelta
import pickle
from special_cases_managerss import SpecialCasesManager
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import json
from datetime import datetime
from pathlib import Path


class SearchLogger:
    def __init__(self, log_file="search_logs.json"):
        self.log_file = log_file
        self.ensure_log_file_exists()

    def ensure_log_file_exists(self):
        # Create the file with an empty list if it doesn't exist or is empty
        if not Path(self.log_file).exists() or Path(self.log_file).stat().st_size == 0:
            with open(self.log_file, 'w') as f:
                json.dump([], f)

    def log_search(self, user_id: int, user_name: str, search_type: str, search_query: str):
        try:
            # First ensure the file exists and has valid JSON
            self.ensure_log_file_exists()

            # Read existing logs
            try:
                with open(self.log_file, 'r') as f:
                    logs = json.load(f)
            except json.JSONDecodeError:
                # If there's an error reading the JSON, start with an empty list
                logs = []

            # Create new log entry
            log_entry = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "user_id": user_id,
                "user_name": user_name,
                "search_type": search_type,
                "search_query": search_query
            }

            # Add new entry
            logs.append(log_entry)

            # Write back to file
            with open(self.log_file, 'w') as f:
                json.dump(logs, f, indent=2)

        except Exception as e:
            print(f"Error logging search: {e}")

    def get_recent_searches(self, limit: int = 100):
        try:
            # First ensure the file exists and has valid JSON
            self.ensure_log_file_exists()

            with open(self.log_file, 'r') as f:
                try:
                    logs = json.load(f)
                except json.JSONDecodeError:
                    return []
            return logs[-limit:]
        except Exception as e:
            print(f"Error getting recent searches: {e}")
            return []


# Create an instance of the logger
search_logger = SearchLogger()


# After your other global variables
special_cases_manager = SpecialCasesManager()

# Initialize some cases if you want (optional)
special_cases_manager.add_case(
    "pushpa 2",
    ["pushpa2", "pushpa-2", "pushpa2therule", "pushpa 2 the rule"],
    [
        {"url": "https://example4.com", "language": "Hindi"},
        {"url": "https://example5.com", "language": "Telugu"}
    ]
)

special_cases_manager.add_case(
    "venom",
    ["venom", "venom1", "venom2"],
    [
        {"url": "https://www.udlinks.com/3I1l", "language": "hindi"}
    ]
)




nest_asyncio.apply()

TELEGRAM_TOKEN = "7883754025:AAHUDU-_EM4QYome14k_28PQbPTWsl_9w6s"
TMDB_API_KEY = "c3b8704a4df65146c194940351efa9a2"
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
DELETE_TIMEOUT = 420  # 7 minutes in seconds
DISCLAIMER = "⚠️ This message will be deleted in 7 minutes"
HORROR_GENRE_ID = 27  # TMDB's genre ID for horror movies



USER_CONTEXT = {}

GENRE_IDS = {
    'horror': 27,
    'crime': 80,
    'romance': 10749
}


class TMDBAPIHandler:
    def __init__(self, api_key, base_url="https://api.themoviedb.org/3"):
        self.api_key = api_key
        self.base_url = base_url
        self.session = self._create_session()

    def _create_session(self):
        session = requests.Session()

        # Configure retry strategy
        retries = Retry(
            total=5,  # Total number of retries
            backoff_factor=0.5,  # Wait 0.5, 1, 2, 4, 8 seconds between retries
            status_forcelist=[500, 502, 503, 504, 408, 429]  # HTTP status codes to retry on
        )

        # Add retry adapter to session
        adapter = HTTPAdapter(max_retries=retries)
        session.mount('http://', adapter)
        session.mount('https://', adapter)

        return session

    def make_request(self, endpoint, params=None):
        if params is None:
            params = {}

        # Always include API key
        params['api_key'] = self.api_key

        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                response = self.session.get(
                    f"{self.base_url}{endpoint}",
                    params=params,
                    timeout=10  # 10 seconds timeout
                )
                response.raise_for_status()
                return response.json()

            except requests.exceptions.ConnectionError as e:
                if attempt == max_attempts - 1:
                    raise Exception("Unable to connect to TMDB API. Please check your internet connection.") from e
                time.sleep(2 ** attempt)  # Exponential backoff

            except requests.exceptions.Timeout as e:
                if attempt == max_attempts - 1:
                    raise Exception("TMDB API request timed out. Please try again later.") from e
                time.sleep(2 ** attempt)

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:  # Rate limit exceeded
                    retry_after = int(e.response.headers.get('Retry-After', 5))
                    time.sleep(retry_after)
                    continue
                raise Exception(f"TMDB API error: {e.response.status_code}") from e


LAST_ACTIVITY_FILE = "user_activity.pkl"
INACTIVITY_THRESHOLD = timedelta(hours=78)


class SearchStatistics:
    def __init__(self, log_file="search_logs.json", stats_file="stastics.txt"):
        self.log_file = log_file
        self.stats_file = stats_file
        self.search_logger = SearchLogger(log_file)
        # Ensure stastics file exists
        self.update_stastics_file()
        print(f"SearchStatistics initialized. Stats file: {stats_file}")

    def _load_searches(self):
        """Load searches from the log file"""
        try:
            with open(self.log_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def get_most_searched(self, days=None):
        """Get most searched queries within specified days"""
        searches = self._load_searches()
        if not searches:
            return []

        # Filter by date if days is specified
        if days:
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            searches = [s for s in searches if s['timestamp'][:10] >= cutoff_date]

        # Count search queries
        query_counts = {}
        for search in searches:
            query = search['search_query'].lower()
            query_counts[query] = query_counts.get(query, 0) + 1

        # Sort by count and return top 10
        return sorted(query_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    def get_user_search_history(self, limit=50):
        """Get recent user search history"""
        searches = self._load_searches()
        return searches[-limit:] if searches else []

    def update_stastics_file(self):  # Changed method name to match file name
        try:
            print(f"Updating stastics file at {datetime.now()}")

            # Check if log file exists and has data
            if not Path(self.log_file).exists():
                print(f"Log file {self.log_file} does not exist!")
                return

            # Load searches
            searches = self._load_searches()
            if not searches:
                print("No search data found in logs")
                stats_text = "No search data available yet.\nLast Updated: " + datetime.now().strftime(
                    '%Y-%m-%d %H:%M:%S')
            else:
                # Get statistics for different time periods
                all_time = self.get_most_searched()
                today = self.get_most_searched(days=1)
                week = self.get_most_searched(days=7)
                year = self.get_most_searched(days=365)
                user_history = self.get_user_search_history(limit=50)

                stats_text = self._format_stastics(all_time, today, week, year, user_history)  # Changed method name

            # Write to stastics file
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                f.write(stats_text)

            print(f"Stastics file updated successfully at {datetime.now()}")

            # Debug: Read and print file contents
            with open(self.stats_file, 'r', encoding='utf-8') as f:
                content = f.read()
            print(f"Stastics file size: {len(content)} bytes")

        except Exception as e:
            print(f"Error updating stastics file: {e}")
            import traceback
            traceback.print_exc()

    def _format_stastics(self, all_time, today, week, year, user_history):  # Changed method name
        stats_text = "Movie Search Stastics\n"  # Changed heading
        stats_text += "=" * 50 + "\n\n"

        # Add section for each time period
        sections = [
            ("All-Time Most Searched Movies:", all_time),
            ("Today's Most Searched Movies:", today),
            ("This Week's Most Searched Movies:", week),
            ("This Year's Most Searched Movies:", year)
        ]

        for title, data in sections:
            stats_text += f"{title}\n"
            if data:
                stats_text += "\n".join(f"{i + 1}. {movie} ({count} searches)"
                                      for i, (movie, count) in enumerate(data))
            else:
                stats_text += "No searches in this period"
            stats_text += "\n\n"

        # Add user history section
        stats_text += "Recent User Search History:\n"
        stats_text += "=" * 50 + "\n"
        if user_history:
            for search in user_history:
                stats_text += f"\nTime: {search['timestamp']}\n"
                stats_text += f"User: {search['user_name']} (ID: {search['user_id']})\n"
                stats_text += f"Search Type: {search['search_type']}\n"
                stats_text += f"Query: {search['search_query']}\n"
                stats_text += "-" * 30 + "\n"
        else:
            stats_text += "\nNo user search history available yet\n"

        stats_text += f"\nLast Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        return stats_text

# Modify the update_statistics_job to include error handling and logging
async def update_stastics_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        print(f"Starting stastics update job at {datetime.now()}")
        stats = SearchStatistics()
        stats.update_stastics_file()
        print(f"Completed stastics update job at {datetime.now()}")
    except Exception as e:
        print(f"Error in stastics update job: {e}")
        import traceback
        traceback.print_exc()

async def view_searches_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only allow yourself to see the searches
    if update.message.from_user.id == 6822829183:  # Replace with your Telegram ID
        recent_searches = search_logger.get_recent_searches(limit=10)  # Get last 10 searches

        message = "Recent Searches:\n\n"
        for search in recent_searches:
            message += f"👤 User: {search['user_name']}\n"
            message += f"🔍 Query: {search['search_query']}\n"
            message += f"⏰ Time: {search['timestamp']}\n"
            message += f"Type: {search['search_type']}\n\n"

        await update.message.reply_text(message)
    else:
        await update.message.reply_text("You don't have permission to use this command.")


# Add this to your command handlers

class UserActivityManager:
    def __init__(self):
        self.user_activity = {}
        self.load_activity()

    def load_activity(self):
        if Path(LAST_ACTIVITY_FILE).exists():
            try:
                with open(LAST_ACTIVITY_FILE, 'rb') as f:
                    self.user_activity = pickle.load(f)
            except Exception as e:
                print(f"Error loading user activity: {e}")
                self.user_activity = {}

    def save_activity(self):
        try:
            with open(LAST_ACTIVITY_FILE, 'wb') as f:
                pickle.dump(self.user_activity, f)
        except Exception as e:
            print(f"Error saving user activity: {e}")

    def update_user_activity(self, user_id: int, user_name: str):
        self.user_activity[user_id] = {
            'last_active': datetime.now(),
            'name': user_name
        }
        self.save_activity()

    def get_inactive_users(self):
        current_time = datetime.now()
        inactive_users = []

        for user_id, data in self.user_activity.items():
            if (current_time - data['last_active']) >= INACTIVITY_THRESHOLD:
                inactive_users.append({
                    'user_id': user_id,
                    'name': data['name'],
                    'last_active': data['last_active']
                })

        return inactive_users


# Create global instance
activity_manager = UserActivityManager()


# Modify the handle_user_message function to track activity
async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    await delete_message_later(context, update.message.chat_id, update.message.message_id)
    await handle_user_query(update, context)


# Add a new function to check for inactive users
async def check_inactive_users(context: ContextTypes.DEFAULT_TYPE):
    inactive_users = activity_manager.get_inactive_users()

    for user in inactive_users:
        try:
            message = f"Hey {user['name']} 👋,\n\nI am missing you dear! 💫\nIt's been a while since we last chatted. Come back and discover some amazing movies! 🎬"

            await context.bot.send_message(
                chat_id=user['user_id'],
                text=message,
                parse_mode='Markdown'
            )

            # Update the last activity to prevent spam
            activity_manager.update_user_activity(user['user_id'], user['name'])

        except Exception as e:
            print(f"Error sending reminder to user {user['user_id']}: {e}")

class MessageTracker:
    def __init__(self):
        self.messages: Dict[int, Dict[int, datetime]] = {}

    async def add_message(self, chat_id: int, message_id: int):
        if chat_id not in self.messages:
            self.messages[chat_id] = {}
        self.messages[chat_id][message_id] = datetime.now() + timedelta(seconds=DELETE_TIMEOUT)

    async def cleanup_messages(self, context: ContextTypes.DEFAULT_TYPE):
        current_time = datetime.now()
        for chat_id in list(self.messages.keys()):
            for message_id, expiry_time in list(self.messages[chat_id].items()):
                if current_time >= expiry_time:
                    try:
                        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                    except TelegramError:
                        pass  # Message might already be deleted
                    finally:
                        del self.messages[chat_id][message_id]
            if not self.messages[chat_id]:
                del self.messages[chat_id]

message_tracker = MessageTracker()

async def cleanup_job(context: ContextTypes.DEFAULT_TYPE):
    await message_tracker.cleanup_messages(context)

async def delete_message_later(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int):
    await message_tracker.add_message(chat_id, message_id)

async def send_with_warning(message, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None, parse_mode=None):
    try:
        if hasattr(message, 'reply_text'):
            sent_message = await message.reply_text(
                f"{text}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await message.edit_text(
                f"{text}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

        await delete_message_later(context, sent_message.chat_id, sent_message.message_id)
        return sent_message
    except TelegramError as e:
        print(f"Error sending message: {e}")
        return None

async def send_photo_with_warning(message, context: ContextTypes.DEFAULT_TYPE, photo: str, caption: str, reply_markup=None, parse_mode=None):
    try:
        if hasattr(message, 'reply_photo'):
            sent_message = await message.reply_photo(
                photo=photo,
                caption=f"{caption}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await context.bot.send_photo(
                chat_id=message.chat_id,
                photo=photo,
                caption=f"{caption}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

        await delete_message_later(context, sent_message.chat_id, sent_message.message_id)
        return sent_message
    except TelegramError as e:
        print(f"Error sending photo: {e}")
        return None


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    keyboard = [
        [InlineKeyboardButton("  DOWNLOAD MOVIES", callback_data='search_movies')],
        [
            InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
            InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
            InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
        ],
        [InlineKeyboardButton("📈 Popular Movies", callback_data='popular'),
         InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
        [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
        [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_with_warning(
        update.message,
        context,
        f"👋 Hello {user_name}! Welcome to @movieshuba11_bot!\n\nClick on /start to restart or type",
        reply_markup=reply_markup
    )

async def show_start_menu(message, context: ContextTypes.DEFAULT_TYPE):
    # Get user's name from the callback query
    user_name = message._effective_user.first_name if hasattr(message, '_effective_user') else "there"
    keyboard = [
        [InlineKeyboardButton(" Download movies", callback_data='search_movies')],
        [
            InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
            InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
            InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
        ],
        [InlineKeyboardButton("📈 Popular Movies", callback_data='popular')],
        [InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
        [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
        [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_with_warning(
        message,
        context,
        f"👋 Hello {user_name}! Welcome to moviieshubb_bot!\n\nClick on /start to restart or type",
        reply_markup=reply_markup
    )



async def get_random_movies_by_genre(message, context: ContextTypes.DEFAULT_TYPE, genre_id=None):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "sort_by": "popularity.desc",
            "page": 1
        }

        if genre_id:
            params["with_genres"] = genre_id

        response = requests.get(url, params=params)
        response.raise_for_status()
        total_pages = min(response.json().get("total_pages", 1), 500)

        random_page = random.randint(1, total_pages)
        params["page"] = random_page

        response = requests.get(url, params=params)
        response.raise_for_status()

        all_movies = response.json().get("results", [])
        random_movies = random.sample(all_movies, min(5, len(all_movies)))

        response_text = "🎲 Random Movie Suggestions:\n\n"
        keyboard = []
        for i, movie in enumerate(random_movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"
            keyboard.append([InlineKeyboardButton(f"🔍 Search {movie['title']}", callback_data=f'search_specific_{movie["id"]}')])

        keyboard.extend([
            [
                InlineKeyboardButton("👻 Horror", callback_data='random_horror'),
                InlineKeyboardButton("🔪 Crime", callback_data='random_crime'),
                InlineKeyboardButton("💝 Romance", callback_data='random_romance')
            ],
            [InlineKeyboardButton("🎲 More Random", callback_data='random_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching random movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='random_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                                "Sorry, couldn't fetch random movies right now.",
                                reply_markup=reply_markup)


async def get_popular_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/movie/popular"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "🎬 Currently Popular Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching popular movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='popular')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch popular movies right now.",
                              reply_markup=reply_markup)

async def get_horror_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "with_genres": HORROR_GENRE_ID,
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "👻 Popular Horror Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton("👻 More Horror Movies", callback_data='horror_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching horror movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='horror_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch horror movies right now.",
                              reply_markup=reply_markup)

async def get_bollywood_popular_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "region": "IN",
            "with_original_language": "hi",
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "🎬  Bollywood Popular Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching Bollywood movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='bollywood_popular')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch Bollywood movies right now.",
                              reply_markup=reply_markup)


async def search_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    special_case, special_links = special_cases_manager.is_special_case(query)
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Log the search
    search_logger.log_search(user_id, user_name, "movie", query)
    try:
        tmdb_handler = TMDBAPIHandler(TMDB_API_KEY)

        # Search for movie
        results = tmdb_handler.make_request(
            "/search/movie",
            params={"query": query, "language": "en-US"}
        ).get("results", [])

        if results:
            movie = results[0]
            movie_id = movie["id"]

            # Get movie details
            movie_details = tmdb_handler.make_request(f"/movie/{movie_id}")
            providers = tmdb_handler.make_request(f"/movie/{movie_id}/watch/providers").get("results", {}).get("US",
                                                                                                               {}).get(
                "flatrate", [])

        search_url = f"{TMDB_BASE_URL}/search/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        if results:
            movie = results[0]
            movie_id = movie["id"]

            details_url = f"{TMDB_BASE_URL}/movie/{movie_id}"
            watch_providers_url = f"{TMDB_BASE_URL}/movie/{movie_id}/watch/providers"

            details_response = requests.get(details_url, params={"api_key": TMDB_API_KEY})
            providers_response = requests.get(watch_providers_url, params={"api_key": TMDB_API_KEY})

            movie_details = details_response.json()
            providers = providers_response.json().get("results", {}).get("US", {}).get("flatrate", [])

            keyboard = [
                [InlineKeyboardButton(" Search Another Movie", callback_data='search_movies')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            response_text = (
                f"*{movie_details['title']}* ({movie_details.get('release_date', '')[:4]})\n\n"
                f"Plot: {movie_details.get('overview', 'No plot available')}\n\n"
            )

            if providers:
                response_text += "Available on: " + ", ".join(p["provider_name"] for p in providers) + "\n\n"
            else:
                response_text += "Streaming information not available\n\n"

            if special_case and special_links:
                response_text += "Download Links:\n"
                for link in special_links:
                    lang_text = f" ({link['language']})" if link.get('language') else ""
                    response_text += f"• {link['url']}{lang_text}\n"
            else:
                response_text += "download link comming soon msg @balaram129"

            if movie_details.get("poster_path"):
                poster_url = f"{TMDB_IMAGE_BASE_URL}{movie_details['poster_path']}"
                await send_photo_with_warning(update.message, context, photo=poster_url, caption=response_text, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                await send_with_warning(update.message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            keyboard = [
                [InlineKeyboardButton(" Try Again", callback_data='search_movies')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(update.message, context, "No movies found matching your search.", reply_markup=reply_markup)
    except Exception as e:
        print(f"Error in movie search: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(update.message, context,
                              "Sorry, there was an error processing your request. Please try again.",
                              reply_markup=reply_markup)

async def search_by_actor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Log the search
    search_logger.log_search(user_id, user_name, "actor", query)
    try:
        search_url = f"{TMDB_BASE_URL}/search/person"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        if results:
            actor = results[0]
            actor_id = actor["id"]

            actor_details_url = f"{TMDB_BASE_URL}/person/{actor_id}"
            movies_url = f"{TMDB_BASE_URL}/person/{actor_id}/movie_credits"

            actor_details_response = requests.get(actor_details_url, params={"api_key": TMDB_API_KEY})
            movies_response = requests.get(movies_url, params={"api_key": TMDB_API_KEY})

            actor_details = actor_details_response.json()
            movies = movies_response.json().get("cast", [])

            movies_with_rating = [m for m in movies if m.get("vote_average", 0) > 0]
            sorted_movies = sorted(movies_with_rating, key=lambda x: x.get("vote_average", 0), reverse=True)

            popular_movies = [m for m in sorted_movies if m.get("vote_average", 0) >= 7][:4]
            unpopular_movies = [m for m in sorted_movies if m.get("vote_average", 0) < 7][:4]

            response_text = f"🎭 {actor['name']}\n"
            if actor_details.get("birthday"):
                response_text += f"Birthday: {actor_details['birthday']}\n"
            if actor_details.get("place_of_birth"):
                response_text += f"Birthplace: {actor_details['place_of_birth']}\n"

            response_text += "\n📈 Highly Rated Movies:\n"
            for i, movie in enumerate(popular_movies, 1):
                response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
                response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"

            response_text += "\n📉 Other Notable Movies:\n"
            for i, movie in enumerate(unpopular_movies, 1):
                response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
                response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"

            keyboard = [
                [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
                [InlineKeyboardButton(" Search Another Actor", callback_data='search_actor')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            if actor.get("profile_path"):
                actor_image_url = f"{TMDB_IMAGE_BASE_URL}{actor['profile_path']}"
                await send_photo_with_warning(
                    update.message,
                    context,
                    photo=actor_image_url,
                    caption=response_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await send_with_warning(
                    update.message,
                    context,
                    response_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
        else:
            keyboard = [
                [InlineKeyboardButton(" Try Again", callback_data='search_actor')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                update.message,
                context,
                "No actor found matching your search.",
                reply_markup=reply_markup
            )
    except Exception as e:
        print(f"Error in actor search: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='search_actor')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(
            update.message,
            context,
            "Sorry, there was an error processing your request. Please try again.",
            reply_markup=reply_markup
        )
def is_special_case(query):
    query_lower = query.lower().strip()
    for key, case in special_cases_manager.items():
        if query_lower == key.lower() or query_lower in [v.lower() for v in case["variants"]]:
            return True, case["links"]
    return False, []

async def get_genre_movies(message, context: ContextTypes.DEFAULT_TYPE, genre_id: int, genre_name: str):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "with_genres": genre_id,
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = f"🎬 Popular {genre_name} Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching {genre_name} movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data=f'genre_{genre_name.lower()}')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              f"Sorry, couldn't fetch {genre_name} movies right now.",
                              reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_name = query.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    try:
        if query.data.startswith('search_specific_'):
            movie_id = query.data.split('_')[2]
            # Get movie details from TMDB
            url = f"{TMDB_BASE_URL}/movie/{movie_id}"
            response = requests.get(url, params={"api_key": TMDB_API_KEY})
            movie = response.json()

            # Create a message with movie details
            movie_text = f"{movie['title']} ({movie.get('release_date', '')[:4]})"

            # Send a temporary message to user's private chat
            class SimulatedMessage:
                def __init__(self, chat_id, text, from_user):
                    self.chat_id = chat_id
                    self.text = text
                    self.from_user = from_user

                def reply_text(self, *args, **kwargs):
                    return query.message.reply_text(*args, **kwargs)

                def reply_photo(self, *args, **kwargs):
                    return query.message.reply_photo(*args, **kwargs)

            # Create a proper message object
            simulated_message = SimulatedMessage(
                chat_id=query.message.chat_id,
                text=movie['title'],
                from_user=query.from_user
            )

            # Create a proper update object
            class SimulatedUpdate:
                def __init__(self, message):
                    self.message = message

            simulated_update = SimulatedUpdate(simulated_message)

            # Perform the search
            await search_movie(simulated_update, context)
            return
        if query.data == 'genre_horror':
            await get_genre_movies(query.message, context, GENRE_IDS['horror'], "Horror")
        elif query.data == 'genre_romance':
            await get_genre_movies(query.message, context, GENRE_IDS['romance'], "Romance")
        elif query.data == 'genre_crime':
            await get_genre_movies(query.message, context, GENRE_IDS['crime'], "Crime")
        elif query.data == 'random_movies':
            await get_random_movies_by_genre(query.message, context)
        if query.data == 'random_movies':
            await get_random_movies_by_genre(query.message, context)
        elif query.data == 'random_horror':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['horror'])
        elif query.data == 'random_crime':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['crime'])
        elif query.data == 'random_romance':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['romance'])
        elif query.data == 'horror_movies':
            await get_horror_movies(query.message, context)
        elif query.data == 'search_movies':
            USER_CONTEXT[query.message.chat_id] = 'movie'
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "🔍 Just type the name of any movie you want to search for!",
                reply_markup=reply_markup
            )
        elif query.data == 'search_actor':
            USER_CONTEXT[query.message.chat_id] = 'actor'
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "🎭 Just type the name of any actor to see their movies!",
                reply_markup=reply_markup
            )
        elif query.data == 'help':
            help_text = ("📖 How to use this bot:\n\n"
                        "1. Simply type any movie name\n"
                        "2. Or type any actor name to find their movies\n"
                        "3. I'll show you the details\n"
                        "4. Check out popular movies in both Hollywood and Bollywood\n"
                        "5. Try our random movie suggestions by genre!\n"
                        "Need more help? Just type /start to see the main menu again! or msg @balaram129")
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                help_text,
                reply_markup=reply_markup
            )
        elif query.data == 'popular':
            await get_popular_movies(query.message, context)
        elif query.data == 'bollywood_popular':
            await get_bollywood_popular_movies(query.message, context)
        elif query.data == 'start_menu':
            keyboard = [
                [InlineKeyboardButton("🔍 Download movies", callback_data='search_movies'),
                 InlineKeyboardButton("👻 Horror Movies", callback_data='horror_movies')],
                [
                    InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
                    InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
                    InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
                ],
                [InlineKeyboardButton("📈 Popular Movies", callback_data='popular')],
                [InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
                [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
                [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
                [InlineKeyboardButton("❓ Help", callback_data='help')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "👋 Welcome to moviieshubb_bot!\n\nClick on /start to restart or type",
                reply_markup=reply_markup
            )

    except Exception as e:
        print(f"Error in button callback: {e}")
        keyboard = [
            [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(
            query.message,
            context,
            "Sorry, there was an error processing your request. Please try again.",
            reply_markup=reply_markup
        )

async def handle_user_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_context = USER_CONTEXT.get(update.message.chat_id, "movie")
    if user_context == "actor":
        await search_by_actor(update, context)
    else:
        await search_movie(update, context)

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_message_later(context, update.message.chat_id, update.message.message_id)
    await handle_user_query(update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Exception while handling an update: {context.error}")
    if isinstance(context.error, Conflict):
        print("Bot instance already running. Exiting...")
        sys.exit(1)
    elif isinstance(context.error, NetworkError):
        print("Network error occurred. Waiting before retry...")
        await asyncio.sleep(1)
    else:
        print(f"Unexpected error: {context.error}")


def main():
    try:
        application = (
            Application.builder()
            .token(TELEGRAM_TOKEN)
            .build()
        )

        # Add existing handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CallbackQueryHandler(button_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))
        application.add_handler(CommandHandler("viewsearches", view_searches_command))

        # Add error handler
        application.add_error_handler(error_handler)

        # Set up the cleanup job to run every 10 seconds
        job_queue = application.job_queue
        job_queue.run_repeating(cleanup_job, interval=10, first=0)

        # Add the inactive user check job (runs every 6 hours)
        job_queue.run_repeating(check_inactive_users, interval=21600, first=21600)

        # Update stastics more frequently (every 5 minutes)
        job_queue.run_repeating(update_stastics_job, interval=300, first=0)

        # Initial statistics update
        print("Performing initial statistics update...")
        stats = SearchStatistics()
        stats.update_stastics_file()
        print("Initial statistics update completed")

        # Start the bot
        print("Starting bot...")
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

    except Exception as e:
        print(f"Error starting bot: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

# Test the logger
logger = SearchLogger()
logger.log_search(123456, "TestUser", "movie", "Avatar")

# Check recent searches
recent = logger.get_recent_searches()
print("Recent searches:", recent)import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import Conflict, NetworkError, TelegramError
import nest_asyncio
import sys
import random
from typing import Optional, Dict
from datetime import datetime, timedelta
import pickle
from special_cases_managerss import SpecialCasesManager
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import json
from datetime import datetime
from pathlib import Path


class SearchLogger:
    def __init__(self, log_file="search_logs.json"):
        self.log_file = log_file
        self.ensure_log_file_exists()

    def ensure_log_file_exists(self):
        # Create the file with an empty list if it doesn't exist or is empty
        if not Path(self.log_file).exists() or Path(self.log_file).stat().st_size == 0:
            with open(self.log_file, 'w') as f:
                json.dump([], f)

    def log_search(self, user_id: int, user_name: str, search_type: str, search_query: str):
        try:
            # First ensure the file exists and has valid JSON
            self.ensure_log_file_exists()

            # Read existing logs
            try:
                with open(self.log_file, 'r') as f:
                    logs = json.load(f)
            except json.JSONDecodeError:
                # If there's an error reading the JSON, start with an empty list
                logs = []

            # Create new log entry
            log_entry = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "user_id": user_id,
                "user_name": user_name,
                "search_type": search_type,
                "search_query": search_query
            }

            # Add new entry
            logs.append(log_entry)

            # Write back to file
            with open(self.log_file, 'w') as f:
                json.dump(logs, f, indent=2)

        except Exception as e:
            print(f"Error logging search: {e}")

    def get_recent_searches(self, limit: int = 100):
        try:
            # First ensure the file exists and has valid JSON
            self.ensure_log_file_exists()

            with open(self.log_file, 'r') as f:
                try:
                    logs = json.load(f)
                except json.JSONDecodeError:
                    return []
            return logs[-limit:]
        except Exception as e:
            print(f"Error getting recent searches: {e}")
            return []


# Create an instance of the logger
search_logger = SearchLogger()


# After your other global variables
special_cases_manager = SpecialCasesManager()

# Initialize some cases if you want (optional)
special_cases_manager.add_case(
    "pushpa 2",
    ["pushpa2", "pushpa-2", "pushpa2therule", "pushpa 2 the rule"],
    [
        {"url": "https://example4.com", "language": "Hindi"},
        {"url": "https://example5.com", "language": "Telugu"}
    ]
)

special_cases_manager.add_case(
    "venom",
    ["venom", "venom1", "venom2"],
    [
        {"url": "https://www.udlinks.com/3I1l", "language": "hindi"}
    ]
)




nest_asyncio.apply()

TELEGRAM_TOKEN = "7883754025:AAHUDU-_EM4QYome14k_28PQbPTWsl_9w6s"
TMDB_API_KEY = "c3b8704a4df65146c194940351efa9a2"
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
DELETE_TIMEOUT = 420  # 7 minutes in seconds
DISCLAIMER = "⚠️ This message will be deleted in 7 minutes"
HORROR_GENRE_ID = 27  # TMDB's genre ID for horror movies



USER_CONTEXT = {}

GENRE_IDS = {
    'horror': 27,
    'crime': 80,
    'romance': 10749
}


class TMDBAPIHandler:
    def __init__(self, api_key, base_url="https://api.themoviedb.org/3"):
        self.api_key = api_key
        self.base_url = base_url
        self.session = self._create_session()

    def _create_session(self):
        session = requests.Session()

        # Configure retry strategy
        retries = Retry(
            total=5,  # Total number of retries
            backoff_factor=0.5,  # Wait 0.5, 1, 2, 4, 8 seconds between retries
            status_forcelist=[500, 502, 503, 504, 408, 429]  # HTTP status codes to retry on
        )

        # Add retry adapter to session
        adapter = HTTPAdapter(max_retries=retries)
        session.mount('http://', adapter)
        session.mount('https://', adapter)

        return session

    def make_request(self, endpoint, params=None):
        if params is None:
            params = {}

        # Always include API key
        params['api_key'] = self.api_key

        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                response = self.session.get(
                    f"{self.base_url}{endpoint}",
                    params=params,
                    timeout=10  # 10 seconds timeout
                )
                response.raise_for_status()
                return response.json()

            except requests.exceptions.ConnectionError as e:
                if attempt == max_attempts - 1:
                    raise Exception("Unable to connect to TMDB API. Please check your internet connection.") from e
                time.sleep(2 ** attempt)  # Exponential backoff

            except requests.exceptions.Timeout as e:
                if attempt == max_attempts - 1:
                    raise Exception("TMDB API request timed out. Please try again later.") from e
                time.sleep(2 ** attempt)

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:  # Rate limit exceeded
                    retry_after = int(e.response.headers.get('Retry-After', 5))
                    time.sleep(retry_after)
                    continue
                raise Exception(f"TMDB API error: {e.response.status_code}") from e


LAST_ACTIVITY_FILE = "user_activity.pkl"
INACTIVITY_THRESHOLD = timedelta(hours=78)


class SearchStatistics:
    def __init__(self, log_file="search_logs.json", stats_file="stastics.txt"):
        self.log_file = log_file
        self.stats_file = stats_file
        self.search_logger = SearchLogger(log_file)
        # Ensure stastics file exists
        self.update_stastics_file()
        print(f"SearchStatistics initialized. Stats file: {stats_file}")

    def _load_searches(self):
        """Load searches from the log file"""
        try:
            with open(self.log_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def get_most_searched(self, days=None):
        """Get most searched queries within specified days"""
        searches = self._load_searches()
        if not searches:
            return []

        # Filter by date if days is specified
        if days:
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            searches = [s for s in searches if s['timestamp'][:10] >= cutoff_date]

        # Count search queries
        query_counts = {}
        for search in searches:
            query = search['search_query'].lower()
            query_counts[query] = query_counts.get(query, 0) + 1

        # Sort by count and return top 10
        return sorted(query_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    def get_user_search_history(self, limit=50):
        """Get recent user search history"""
        searches = self._load_searches()
        return searches[-limit:] if searches else []

    def update_stastics_file(self):  # Changed method name to match file name
        try:
            print(f"Updating stastics file at {datetime.now()}")

            # Check if log file exists and has data
            if not Path(self.log_file).exists():
                print(f"Log file {self.log_file} does not exist!")
                return

            # Load searches
            searches = self._load_searches()
            if not searches:
                print("No search data found in logs")
                stats_text = "No search data available yet.\nLast Updated: " + datetime.now().strftime(
                    '%Y-%m-%d %H:%M:%S')
            else:
                # Get statistics for different time periods
                all_time = self.get_most_searched()
                today = self.get_most_searched(days=1)
                week = self.get_most_searched(days=7)
                year = self.get_most_searched(days=365)
                user_history = self.get_user_search_history(limit=50)

                stats_text = self._format_stastics(all_time, today, week, year, user_history)  # Changed method name

            # Write to stastics file
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                f.write(stats_text)

            print(f"Stastics file updated successfully at {datetime.now()}")

            # Debug: Read and print file contents
            with open(self.stats_file, 'r', encoding='utf-8') as f:
                content = f.read()
            print(f"Stastics file size: {len(content)} bytes")

        except Exception as e:
            print(f"Error updating stastics file: {e}")
            import traceback
            traceback.print_exc()

    def _format_stastics(self, all_time, today, week, year, user_history):  # Changed method name
        stats_text = "Movie Search Stastics\n"  # Changed heading
        stats_text += "=" * 50 + "\n\n"

        # Add section for each time period
        sections = [
            ("All-Time Most Searched Movies:", all_time),
            ("Today's Most Searched Movies:", today),
            ("This Week's Most Searched Movies:", week),
            ("This Year's Most Searched Movies:", year)
        ]

        for title, data in sections:
            stats_text += f"{title}\n"
            if data:
                stats_text += "\n".join(f"{i + 1}. {movie} ({count} searches)"
                                      for i, (movie, count) in enumerate(data))
            else:
                stats_text += "No searches in this period"
            stats_text += "\n\n"

        # Add user history section
        stats_text += "Recent User Search History:\n"
        stats_text += "=" * 50 + "\n"
        if user_history:
            for search in user_history:
                stats_text += f"\nTime: {search['timestamp']}\n"
                stats_text += f"User: {search['user_name']} (ID: {search['user_id']})\n"
                stats_text += f"Search Type: {search['search_type']}\n"
                stats_text += f"Query: {search['search_query']}\n"
                stats_text += "-" * 30 + "\n"
        else:
            stats_text += "\nNo user search history available yet\n"

        stats_text += f"\nLast Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        return stats_text

# Modify the update_statistics_job to include error handling and logging
async def update_stastics_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        print(f"Starting stastics update job at {datetime.now()}")
        stats = SearchStatistics()
        stats.update_stastics_file()
        print(f"Completed stastics update job at {datetime.now()}")
    except Exception as e:
        print(f"Error in stastics update job: {e}")
        import traceback
        traceback.print_exc()

async def view_searches_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only allow yourself to see the searches
    if update.message.from_user.id == 6822829183:  # Replace with your Telegram ID
        recent_searches = search_logger.get_recent_searches(limit=10)  # Get last 10 searches

        message = "Recent Searches:\n\n"
        for search in recent_searches:
            message += f"👤 User: {search['user_name']}\n"
            message += f"🔍 Query: {search['search_query']}\n"
            message += f"⏰ Time: {search['timestamp']}\n"
            message += f"Type: {search['search_type']}\n\n"

        await update.message.reply_text(message)
    else:
        await update.message.reply_text("You don't have permission to use this command.")


# Add this to your command handlers

class UserActivityManager:
    def __init__(self):
        self.user_activity = {}
        self.load_activity()

    def load_activity(self):
        if Path(LAST_ACTIVITY_FILE).exists():
            try:
                with open(LAST_ACTIVITY_FILE, 'rb') as f:
                    self.user_activity = pickle.load(f)
            except Exception as e:
                print(f"Error loading user activity: {e}")
                self.user_activity = {}

    def save_activity(self):
        try:
            with open(LAST_ACTIVITY_FILE, 'wb') as f:
                pickle.dump(self.user_activity, f)
        except Exception as e:
            print(f"Error saving user activity: {e}")

    def update_user_activity(self, user_id: int, user_name: str):
        self.user_activity[user_id] = {
            'last_active': datetime.now(),
            'name': user_name
        }
        self.save_activity()

    def get_inactive_users(self):
        current_time = datetime.now()
        inactive_users = []

        for user_id, data in self.user_activity.items():
            if (current_time - data['last_active']) >= INACTIVITY_THRESHOLD:
                inactive_users.append({
                    'user_id': user_id,
                    'name': data['name'],
                    'last_active': data['last_active']
                })

        return inactive_users


# Create global instance
activity_manager = UserActivityManager()


# Modify the handle_user_message function to track activity
async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    await delete_message_later(context, update.message.chat_id, update.message.message_id)
    await handle_user_query(update, context)


# Add a new function to check for inactive users
async def check_inactive_users(context: ContextTypes.DEFAULT_TYPE):
    inactive_users = activity_manager.get_inactive_users()

    for user in inactive_users:
        try:
            message = f"Hey {user['name']} 👋,\n\nI am missing you dear! 💫\nIt's been a while since we last chatted. Come back and discover some amazing movies! 🎬"

            await context.bot.send_message(
                chat_id=user['user_id'],
                text=message,
                parse_mode='Markdown'
            )

            # Update the last activity to prevent spam
            activity_manager.update_user_activity(user['user_id'], user['name'])

        except Exception as e:
            print(f"Error sending reminder to user {user['user_id']}: {e}")

class MessageTracker:
    def __init__(self):
        self.messages: Dict[int, Dict[int, datetime]] = {}

    async def add_message(self, chat_id: int, message_id: int):
        if chat_id not in self.messages:
            self.messages[chat_id] = {}
        self.messages[chat_id][message_id] = datetime.now() + timedelta(seconds=DELETE_TIMEOUT)

    async def cleanup_messages(self, context: ContextTypes.DEFAULT_TYPE):
        current_time = datetime.now()
        for chat_id in list(self.messages.keys()):
            for message_id, expiry_time in list(self.messages[chat_id].items()):
                if current_time >= expiry_time:
                    try:
                        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                    except TelegramError:
                        pass  # Message might already be deleted
                    finally:
                        del self.messages[chat_id][message_id]
            if not self.messages[chat_id]:
                del self.messages[chat_id]

message_tracker = MessageTracker()

async def cleanup_job(context: ContextTypes.DEFAULT_TYPE):
    await message_tracker.cleanup_messages(context)

async def delete_message_later(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int):
    await message_tracker.add_message(chat_id, message_id)

async def send_with_warning(message, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None, parse_mode=None):
    try:
        if hasattr(message, 'reply_text'):
            sent_message = await message.reply_text(
                f"{text}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await message.edit_text(
                f"{text}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

        await delete_message_later(context, sent_message.chat_id, sent_message.message_id)
        return sent_message
    except TelegramError as e:
        print(f"Error sending message: {e}")
        return None

async def send_photo_with_warning(message, context: ContextTypes.DEFAULT_TYPE, photo: str, caption: str, reply_markup=None, parse_mode=None):
    try:
        if hasattr(message, 'reply_photo'):
            sent_message = await message.reply_photo(
                photo=photo,
                caption=f"{caption}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await context.bot.send_photo(
                chat_id=message.chat_id,
                photo=photo,
                caption=f"{caption}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

        await delete_message_later(context, sent_message.chat_id, sent_message.message_id)
        return sent_message
    except TelegramError as e:
        print(f"Error sending photo: {e}")
        return None


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    keyboard = [
        [InlineKeyboardButton("  DOWNLOAD MOVIES", callback_data='search_movies')],
        [
            InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
            InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
            InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
        ],
        [InlineKeyboardButton("📈 Popular Movies", callback_data='popular'),
         InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
        [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
        [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_with_warning(
        update.message,
        context,
        f"👋 Hello {user_name}! Welcome to @movieshuba11_bot!\n\nClick on /start to restart or type",
        reply_markup=reply_markup
    )

async def show_start_menu(message, context: ContextTypes.DEFAULT_TYPE):
    # Get user's name from the callback query
    user_name = message._effective_user.first_name if hasattr(message, '_effective_user') else "there"
    keyboard = [
        [InlineKeyboardButton(" Download movies", callback_data='search_movies')],
        [
            InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
            InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
            InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
        ],
        [InlineKeyboardButton("📈 Popular Movies", callback_data='popular')],
        [InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
        [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
        [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_with_warning(
        message,
        context,
        f"👋 Hello {user_name}! Welcome to moviieshubb_bot!\n\nClick on /start to restart or type",
        reply_markup=reply_markup
    )



async def get_random_movies_by_genre(message, context: ContextTypes.DEFAULT_TYPE, genre_id=None):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "sort_by": "popularity.desc",
            "page": 1
        }

        if genre_id:
            params["with_genres"] = genre_id

        response = requests.get(url, params=params)
        response.raise_for_status()
        total_pages = min(response.json().get("total_pages", 1), 500)

        random_page = random.randint(1, total_pages)
        params["page"] = random_page

        response = requests.get(url, params=params)
        response.raise_for_status()

        all_movies = response.json().get("results", [])
        random_movies = random.sample(all_movies, min(5, len(all_movies)))

        response_text = "🎲 Random Movie Suggestions:\n\n"
        keyboard = []
        for i, movie in enumerate(random_movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"
            keyboard.append([InlineKeyboardButton(f"🔍 Search {movie['title']}", callback_data=f'search_specific_{movie["id"]}')])

        keyboard.extend([
            [
                InlineKeyboardButton("👻 Horror", callback_data='random_horror'),
                InlineKeyboardButton("🔪 Crime", callback_data='random_crime'),
                InlineKeyboardButton("💝 Romance", callback_data='random_romance')
            ],
            [InlineKeyboardButton("🎲 More Random", callback_data='random_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching random movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='random_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                                "Sorry, couldn't fetch random movies right now.",
                                reply_markup=reply_markup)


async def get_popular_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/movie/popular"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "🎬 Currently Popular Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching popular movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='popular')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch popular movies right now.",
                              reply_markup=reply_markup)

async def get_horror_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "with_genres": HORROR_GENRE_ID,
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "👻 Popular Horror Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton("👻 More Horror Movies", callback_data='horror_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching horror movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='horror_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch horror movies right now.",
                              reply_markup=reply_markup)

async def get_bollywood_popular_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "region": "IN",
            "with_original_language": "hi",
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "🎬  Bollywood Popular Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching Bollywood movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='bollywood_popular')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch Bollywood movies right now.",
                              reply_markup=reply_markup)


async def search_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    special_case, special_links = special_cases_manager.is_special_case(query)
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Log the search
    search_logger.log_search(user_id, user_name, "movie", query)
    try:
        tmdb_handler = TMDBAPIHandler(TMDB_API_KEY)

        # Search for movie
        results = tmdb_handler.make_request(
            "/search/movie",
            params={"query": query, "language": "en-US"}
        ).get("results", [])

        if results:
            movie = results[0]
            movie_id = movie["id"]

            # Get movie details
            movie_details = tmdb_handler.make_request(f"/movie/{movie_id}")
            providers = tmdb_handler.make_request(f"/movie/{movie_id}/watch/providers").get("results", {}).get("US",
                                                                                                               {}).get(
                "flatrate", [])

        search_url = f"{TMDB_BASE_URL}/search/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        if results:
            movie = results[0]
            movie_id = movie["id"]

            details_url = f"{TMDB_BASE_URL}/movie/{movie_id}"
            watch_providers_url = f"{TMDB_BASE_URL}/movie/{movie_id}/watch/providers"

            details_response = requests.get(details_url, params={"api_key": TMDB_API_KEY})
            providers_response = requests.get(watch_providers_url, params={"api_key": TMDB_API_KEY})

            movie_details = details_response.json()
            providers = providers_response.json().get("results", {}).get("US", {}).get("flatrate", [])

            keyboard = [
                [InlineKeyboardButton(" Search Another Movie", callback_data='search_movies')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            response_text = (
                f"*{movie_details['title']}* ({movie_details.get('release_date', '')[:4]})\n\n"
                f"Plot: {movie_details.get('overview', 'No plot available')}\n\n"
            )

            if providers:
                response_text += "Available on: " + ", ".join(p["provider_name"] for p in providers) + "\n\n"
            else:
                response_text += "Streaming information not available\n\n"

            if special_case and special_links:
                response_text += "Download Links:\n"
                for link in special_links:
                    lang_text = f" ({link['language']})" if link.get('language') else ""
                    response_text += f"• {link['url']}{lang_text}\n"
            else:
                response_text += "download link comming soon msg @balaram129"

            if movie_details.get("poster_path"):
                poster_url = f"{TMDB_IMAGE_BASE_URL}{movie_details['poster_path']}"
                await send_photo_with_warning(update.message, context, photo=poster_url, caption=response_text, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                await send_with_warning(update.message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            keyboard = [
                [InlineKeyboardButton(" Try Again", callback_data='search_movies')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(update.message, context, "No movies found matching your search.", reply_markup=reply_markup)
    except Exception as e:
        print(f"Error in movie search: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(update.message, context,
                              "Sorry, there was an error processing your request. Please try again.",
                              reply_markup=reply_markup)

async def search_by_actor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Log the search
    search_logger.log_search(user_id, user_name, "actor", query)
    try:
        search_url = f"{TMDB_BASE_URL}/search/person"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        if results:
            actor = results[0]
            actor_id = actor["id"]

            actor_details_url = f"{TMDB_BASE_URL}/person/{actor_id}"
            movies_url = f"{TMDB_BASE_URL}/person/{actor_id}/movie_credits"

            actor_details_response = requests.get(actor_details_url, params={"api_key": TMDB_API_KEY})
            movies_response = requests.get(movies_url, params={"api_key": TMDB_API_KEY})

            actor_details = actor_details_response.json()
            movies = movies_response.json().get("cast", [])

            movies_with_rating = [m for m in movies if m.get("vote_average", 0) > 0]
            sorted_movies = sorted(movies_with_rating, key=lambda x: x.get("vote_average", 0), reverse=True)

            popular_movies = [m for m in sorted_movies if m.get("vote_average", 0) >= 7][:4]
            unpopular_movies = [m for m in sorted_movies if m.get("vote_average", 0) < 7][:4]

            response_text = f"🎭 {actor['name']}\n"
            if actor_details.get("birthday"):
                response_text += f"Birthday: {actor_details['birthday']}\n"
            if actor_details.get("place_of_birth"):
                response_text += f"Birthplace: {actor_details['place_of_birth']}\n"

            response_text += "\n📈 Highly Rated Movies:\n"
            for i, movie in enumerate(popular_movies, 1):
                response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
                response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"

            response_text += "\n📉 Other Notable Movies:\n"
            for i, movie in enumerate(unpopular_movies, 1):
                response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
                response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"

            keyboard = [
                [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
                [InlineKeyboardButton(" Search Another Actor", callback_data='search_actor')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            if actor.get("profile_path"):
                actor_image_url = f"{TMDB_IMAGE_BASE_URL}{actor['profile_path']}"
                await send_photo_with_warning(
                    update.message,
                    context,
                    photo=actor_image_url,
                    caption=response_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await send_with_warning(
                    update.message,
                    context,
                    response_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
        else:
            keyboard = [
                [InlineKeyboardButton(" Try Again", callback_data='search_actor')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                update.message,
                context,
                "No actor found matching your search.",
                reply_markup=reply_markup
            )
    except Exception as e:
        print(f"Error in actor search: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='search_actor')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(
            update.message,
            context,
            "Sorry, there was an error processing your request. Please try again.",
            reply_markup=reply_markup
        )
def is_special_case(query):
    query_lower = query.lower().strip()
    for key, case in special_cases_manager.items():
        if query_lower == key.lower() or query_lower in [v.lower() for v in case["variants"]]:
            return True, case["links"]
    return False, []

async def get_genre_movies(message, context: ContextTypes.DEFAULT_TYPE, genre_id: int, genre_name: str):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "with_genres": genre_id,
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = f"🎬 Popular {genre_name} Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching {genre_name} movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data=f'genre_{genre_name.lower()}')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              f"Sorry, couldn't fetch {genre_name} movies right now.",
                              reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_name = query.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    try:
        if query.data.startswith('search_specific_'):
            movie_id = query.data.split('_')[2]
            # Get movie details from TMDB
            url = f"{TMDB_BASE_URL}/movie/{movie_id}"
            response = requests.get(url, params={"api_key": TMDB_API_KEY})
            movie = response.json()

            # Create a message with movie details
            movie_text = f"{movie['title']} ({movie.get('release_date', '')[:4]})"

            # Send a temporary message to user's private chat
            class SimulatedMessage:
                def __init__(self, chat_id, text, from_user):
                    self.chat_id = chat_id
                    self.text = text
                    self.from_user = from_user

                def reply_text(self, *args, **kwargs):
                    return query.message.reply_text(*args, **kwargs)

                def reply_photo(self, *args, **kwargs):
                    return query.message.reply_photo(*args, **kwargs)

            # Create a proper message object
            simulated_message = SimulatedMessage(
                chat_id=query.message.chat_id,
                text=movie['title'],
                from_user=query.from_user
            )

            # Create a proper update object
            class SimulatedUpdate:
                def __init__(self, message):
                    self.message = message

            simulated_update = SimulatedUpdate(simulated_message)

            # Perform the search
            await search_movie(simulated_update, context)
            return
        if query.data == 'genre_horror':
            await get_genre_movies(query.message, context, GENRE_IDS['horror'], "Horror")
        elif query.data == 'genre_romance':
            await get_genre_movies(query.message, context, GENRE_IDS['romance'], "Romance")
        elif query.data == 'genre_crime':
            await get_genre_movies(query.message, context, GENRE_IDS['crime'], "Crime")
        elif query.data == 'random_movies':
            await get_random_movies_by_genre(query.message, context)
        if query.data == 'random_movies':
            await get_random_movies_by_genre(query.message, context)
        elif query.data == 'random_horror':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['horror'])
        elif query.data == 'random_crime':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['crime'])
        elif query.data == 'random_romance':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['romance'])
        elif query.data == 'horror_movies':
            await get_horror_movies(query.message, context)
        elif query.data == 'search_movies':
            USER_CONTEXT[query.message.chat_id] = 'movie'
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "🔍 Just type the name of any movie you want to search for!",
                reply_markup=reply_markup
            )
        elif query.data == 'search_actor':
            USER_CONTEXT[query.message.chat_id] = 'actor'
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "🎭 Just type the name of any actor to see their movies!",
                reply_markup=reply_markup
            )
        elif query.data == 'help':
            help_text = ("📖 How to use this bot:\n\n"
                        "1. Simply type any movie name\n"
                        "2. Or type any actor name to find their movies\n"
                        "3. I'll show you the details\n"
                        "4. Check out popular movies in both Hollywood and Bollywood\n"
                        "5. Try our random movie suggestions by genre!\n"
                        "Need more help? Just type /start to see the main menu again! or msg @balaram129")
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                help_text,
                reply_markup=reply_markup
            )
        elif query.data == 'popular':
            await get_popular_movies(query.message, context)
        elif query.data == 'bollywood_popular':
            await get_bollywood_popular_movies(query.message, context)
        elif query.data == 'start_menu':
            keyboard = [
                [InlineKeyboardButton("🔍 Download movies", callback_data='search_movies'),
                 InlineKeyboardButton("👻 Horror Movies", callback_data='horror_movies')],
                [
                    InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
                    InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
                    InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
                ],
                [InlineKeyboardButton("📈 Popular Movies", callback_data='popular')],
                [InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
                [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
                [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
                [InlineKeyboardButton("❓ Help", callback_data='help')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "👋 Welcome to moviieshubb_bot!\n\nClick on /start to restart or type",
                reply_markup=reply_markup
            )

    except Exception as e:
        print(f"Error in button callback: {e}")
        keyboard = [
            [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(
            query.message,
            context,
            "Sorry, there was an error processing your request. Please try again.",
            reply_markup=reply_markup
        )

async def handle_user_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_context = USER_CONTEXT.get(update.message.chat_id, "movie")
    if user_context == "actor":
        await search_by_actor(update, context)
    else:
        await search_movie(update, context)

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_message_later(context, update.message.chat_id, update.message.message_id)
    await handle_user_query(update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Exception while handling an update: {context.error}")
    if isinstance(context.error, Conflict):
        print("Bot instance already running. Exiting...")
        sys.exit(1)
    elif isinstance(context.error, NetworkError):
        print("Network error occurred. Waiting before retry...")
        await asyncio.sleep(1)
    else:
        print(f"Unexpected error: {context.error}")


def main():
    try:
        application = (
            Application.builder()
            .token(TELEGRAM_TOKEN)
            .build()
        )

        # Add existing handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CallbackQueryHandler(button_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))
        application.add_handler(CommandHandler("viewsearches", view_searches_command))

        # Add error handler
        application.add_error_handler(error_handler)

        # Set up the cleanup job to run every 10 seconds
        job_queue = application.job_queue
        job_queue.run_repeating(cleanup_job, interval=10, first=0)

        # Add the inactive user check job (runs every 6 hours)
        job_queue.run_repeating(check_inactive_users, interval=21600, first=21600)

        # Update stastics more frequently (every 5 minutes)
        job_queue.run_repeating(update_stastics_job, interval=300, first=0)

        # Initial statistics update
        print("Performing initial statistics update...")
        stats = SearchStatistics()
        stats.update_stastics_file()
        print("Initial statistics update completed")

        # Start the bot
        print("Starting bot...")
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

    except Exception as e:
        print(f"Error starting bot: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

# Test the logger
logger = SearchLogger()
logger.log_search(123456, "TestUser", "movie", "Avatar")

# Check recent searches
recent = logger.get_recent_searches()
print("Recent searches:", recent)import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import Conflict, NetworkError, TelegramError
import nest_asyncio
import sys
import random
from typing import Optional, Dict
from datetime import datetime, timedelta
import pickle
from special_cases_managerss import SpecialCasesManager
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import json
from datetime import datetime
from pathlib import Path


class SearchLogger:
    def __init__(self, log_file="search_logs.json"):
        self.log_file = log_file
        self.ensure_log_file_exists()

    def ensure_log_file_exists(self):
        # Create the file with an empty list if it doesn't exist or is empty
        if not Path(self.log_file).exists() or Path(self.log_file).stat().st_size == 0:
            with open(self.log_file, 'w') as f:
                json.dump([], f)

    def log_search(self, user_id: int, user_name: str, search_type: str, search_query: str):
        try:
            # First ensure the file exists and has valid JSON
            self.ensure_log_file_exists()

            # Read existing logs
            try:
                with open(self.log_file, 'r') as f:
                    logs = json.load(f)
            except json.JSONDecodeError:
                # If there's an error reading the JSON, start with an empty list
                logs = []

            # Create new log entry
            log_entry = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "user_id": user_id,
                "user_name": user_name,
                "search_type": search_type,
                "search_query": search_query
            }

            # Add new entry
            logs.append(log_entry)

            # Write back to file
            with open(self.log_file, 'w') as f:
                json.dump(logs, f, indent=2)

        except Exception as e:
            print(f"Error logging search: {e}")

    def get_recent_searches(self, limit: int = 100):
        try:
            # First ensure the file exists and has valid JSON
            self.ensure_log_file_exists()

            with open(self.log_file, 'r') as f:
                try:
                    logs = json.load(f)
                except json.JSONDecodeError:
                    return []
            return logs[-limit:]
        except Exception as e:
            print(f"Error getting recent searches: {e}")
            return []


# Create an instance of the logger
search_logger = SearchLogger()


# After your other global variables
special_cases_manager = SpecialCasesManager()

# Initialize some cases if you want (optional)
special_cases_manager.add_case(
    "pushpa 2",
    ["pushpa2", "pushpa-2", "pushpa2therule", "pushpa 2 the rule"],
    [
        {"url": "https://example4.com", "language": "Hindi"},
        {"url": "https://example5.com", "language": "Telugu"}
    ]
)

special_cases_manager.add_case(
    "venom",
    ["venom", "venom1", "venom2"],
    [
        {"url": "https://www.udlinks.com/3I1l", "language": "hindi"}
    ]
)




nest_asyncio.apply()

TELEGRAM_TOKEN = "7883754025:AAHUDU-_EM4QYome14k_28PQbPTWsl_9w6s"
TMDB_API_KEY = "c3b8704a4df65146c194940351efa9a2"
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
DELETE_TIMEOUT = 420  # 7 minutes in seconds
DISCLAIMER = "⚠️ This message will be deleted in 7 minutes"
HORROR_GENRE_ID = 27  # TMDB's genre ID for horror movies



USER_CONTEXT = {}

GENRE_IDS = {
    'horror': 27,
    'crime': 80,
    'romance': 10749
}


class TMDBAPIHandler:
    def __init__(self, api_key, base_url="https://api.themoviedb.org/3"):
        self.api_key = api_key
        self.base_url = base_url
        self.session = self._create_session()

    def _create_session(self):
        session = requests.Session()

        # Configure retry strategy
        retries = Retry(
            total=5,  # Total number of retries
            backoff_factor=0.5,  # Wait 0.5, 1, 2, 4, 8 seconds between retries
            status_forcelist=[500, 502, 503, 504, 408, 429]  # HTTP status codes to retry on
        )

        # Add retry adapter to session
        adapter = HTTPAdapter(max_retries=retries)
        session.mount('http://', adapter)
        session.mount('https://', adapter)

        return session

    def make_request(self, endpoint, params=None):
        if params is None:
            params = {}

        # Always include API key
        params['api_key'] = self.api_key

        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                response = self.session.get(
                    f"{self.base_url}{endpoint}",
                    params=params,
                    timeout=10  # 10 seconds timeout
                )
                response.raise_for_status()
                return response.json()

            except requests.exceptions.ConnectionError as e:
                if attempt == max_attempts - 1:
                    raise Exception("Unable to connect to TMDB API. Please check your internet connection.") from e
                time.sleep(2 ** attempt)  # Exponential backoff

            except requests.exceptions.Timeout as e:
                if attempt == max_attempts - 1:
                    raise Exception("TMDB API request timed out. Please try again later.") from e
                time.sleep(2 ** attempt)

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:  # Rate limit exceeded
                    retry_after = int(e.response.headers.get('Retry-After', 5))
                    time.sleep(retry_after)
                    continue
                raise Exception(f"TMDB API error: {e.response.status_code}") from e


LAST_ACTIVITY_FILE = "user_activity.pkl"
INACTIVITY_THRESHOLD = timedelta(hours=78)


class SearchStatistics:
    def __init__(self, log_file="search_logs.json", stats_file="stastics.txt"):
        self.log_file = log_file
        self.stats_file = stats_file
        self.search_logger = SearchLogger(log_file)
        # Ensure stastics file exists
        self.update_stastics_file()
        print(f"SearchStatistics initialized. Stats file: {stats_file}")

    def _load_searches(self):
        """Load searches from the log file"""
        try:
            with open(self.log_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def get_most_searched(self, days=None):
        """Get most searched queries within specified days"""
        searches = self._load_searches()
        if not searches:
            return []

        # Filter by date if days is specified
        if days:
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            searches = [s for s in searches if s['timestamp'][:10] >= cutoff_date]

        # Count search queries
        query_counts = {}
        for search in searches:
            query = search['search_query'].lower()
            query_counts[query] = query_counts.get(query, 0) + 1

        # Sort by count and return top 10
        return sorted(query_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    def get_user_search_history(self, limit=50):
        """Get recent user search history"""
        searches = self._load_searches()
        return searches[-limit:] if searches else []

    def update_stastics_file(self):  # Changed method name to match file name
        try:
            print(f"Updating stastics file at {datetime.now()}")

            # Check if log file exists and has data
            if not Path(self.log_file).exists():
                print(f"Log file {self.log_file} does not exist!")
                return

            # Load searches
            searches = self._load_searches()
            if not searches:
                print("No search data found in logs")
                stats_text = "No search data available yet.\nLast Updated: " + datetime.now().strftime(
                    '%Y-%m-%d %H:%M:%S')
            else:
                # Get statistics for different time periods
                all_time = self.get_most_searched()
                today = self.get_most_searched(days=1)
                week = self.get_most_searched(days=7)
                year = self.get_most_searched(days=365)
                user_history = self.get_user_search_history(limit=50)

                stats_text = self._format_stastics(all_time, today, week, year, user_history)  # Changed method name

            # Write to stastics file
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                f.write(stats_text)

            print(f"Stastics file updated successfully at {datetime.now()}")

            # Debug: Read and print file contents
            with open(self.stats_file, 'r', encoding='utf-8') as f:
                content = f.read()
            print(f"Stastics file size: {len(content)} bytes")

        except Exception as e:
            print(f"Error updating stastics file: {e}")
            import traceback
            traceback.print_exc()

    def _format_stastics(self, all_time, today, week, year, user_history):  # Changed method name
        stats_text = "Movie Search Stastics\n"  # Changed heading
        stats_text += "=" * 50 + "\n\n"

        # Add section for each time period
        sections = [
            ("All-Time Most Searched Movies:", all_time),
            ("Today's Most Searched Movies:", today),
            ("This Week's Most Searched Movies:", week),
            ("This Year's Most Searched Movies:", year)
        ]

        for title, data in sections:
            stats_text += f"{title}\n"
            if data:
                stats_text += "\n".join(f"{i + 1}. {movie} ({count} searches)"
                                      for i, (movie, count) in enumerate(data))
            else:
                stats_text += "No searches in this period"
            stats_text += "\n\n"

        # Add user history section
        stats_text += "Recent User Search History:\n"
        stats_text += "=" * 50 + "\n"
        if user_history:
            for search in user_history:
                stats_text += f"\nTime: {search['timestamp']}\n"
                stats_text += f"User: {search['user_name']} (ID: {search['user_id']})\n"
                stats_text += f"Search Type: {search['search_type']}\n"
                stats_text += f"Query: {search['search_query']}\n"
                stats_text += "-" * 30 + "\n"
        else:
            stats_text += "\nNo user search history available yet\n"

        stats_text += f"\nLast Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        return stats_text

# Modify the update_statistics_job to include error handling and logging
async def update_stastics_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        print(f"Starting stastics update job at {datetime.now()}")
        stats = SearchStatistics()
        stats.update_stastics_file()
        print(f"Completed stastics update job at {datetime.now()}")
    except Exception as e:
        print(f"Error in stastics update job: {e}")
        import traceback
        traceback.print_exc()

async def view_searches_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only allow yourself to see the searches
    if update.message.from_user.id == 6822829183:  # Replace with your Telegram ID
        recent_searches = search_logger.get_recent_searches(limit=10)  # Get last 10 searches

        message = "Recent Searches:\n\n"
        for search in recent_searches:
            message += f"👤 User: {search['user_name']}\n"
            message += f"🔍 Query: {search['search_query']}\n"
            message += f"⏰ Time: {search['timestamp']}\n"
            message += f"Type: {search['search_type']}\n\n"

        await update.message.reply_text(message)
    else:
        await update.message.reply_text("You don't have permission to use this command.")


# Add this to your command handlers

class UserActivityManager:
    def __init__(self):
        self.user_activity = {}
        self.load_activity()

    def load_activity(self):
        if Path(LAST_ACTIVITY_FILE).exists():
            try:
                with open(LAST_ACTIVITY_FILE, 'rb') as f:
                    self.user_activity = pickle.load(f)
            except Exception as e:
                print(f"Error loading user activity: {e}")
                self.user_activity = {}

    def save_activity(self):
        try:
            with open(LAST_ACTIVITY_FILE, 'wb') as f:
                pickle.dump(self.user_activity, f)
        except Exception as e:
            print(f"Error saving user activity: {e}")

    def update_user_activity(self, user_id: int, user_name: str):
        self.user_activity[user_id] = {
            'last_active': datetime.now(),
            'name': user_name
        }
        self.save_activity()

    def get_inactive_users(self):
        current_time = datetime.now()
        inactive_users = []

        for user_id, data in self.user_activity.items():
            if (current_time - data['last_active']) >= INACTIVITY_THRESHOLD:
                inactive_users.append({
                    'user_id': user_id,
                    'name': data['name'],
                    'last_active': data['last_active']
                })

        return inactive_users


# Create global instance
activity_manager = UserActivityManager()


# Modify the handle_user_message function to track activity
async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    await delete_message_later(context, update.message.chat_id, update.message.message_id)
    await handle_user_query(update, context)


# Add a new function to check for inactive users
async def check_inactive_users(context: ContextTypes.DEFAULT_TYPE):
    inactive_users = activity_manager.get_inactive_users()

    for user in inactive_users:
        try:
            message = f"Hey {user['name']} 👋,\n\nI am missing you dear! 💫\nIt's been a while since we last chatted. Come back and discover some amazing movies! 🎬"

            await context.bot.send_message(
                chat_id=user['user_id'],
                text=message,
                parse_mode='Markdown'
            )

            # Update the last activity to prevent spam
            activity_manager.update_user_activity(user['user_id'], user['name'])

        except Exception as e:
            print(f"Error sending reminder to user {user['user_id']}: {e}")

class MessageTracker:
    def __init__(self):
        self.messages: Dict[int, Dict[int, datetime]] = {}

    async def add_message(self, chat_id: int, message_id: int):
        if chat_id not in self.messages:
            self.messages[chat_id] = {}
        self.messages[chat_id][message_id] = datetime.now() + timedelta(seconds=DELETE_TIMEOUT)

    async def cleanup_messages(self, context: ContextTypes.DEFAULT_TYPE):
        current_time = datetime.now()
        for chat_id in list(self.messages.keys()):
            for message_id, expiry_time in list(self.messages[chat_id].items()):
                if current_time >= expiry_time:
                    try:
                        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                    except TelegramError:
                        pass  # Message might already be deleted
                    finally:
                        del self.messages[chat_id][message_id]
            if not self.messages[chat_id]:
                del self.messages[chat_id]

message_tracker = MessageTracker()

async def cleanup_job(context: ContextTypes.DEFAULT_TYPE):
    await message_tracker.cleanup_messages(context)

async def delete_message_later(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int):
    await message_tracker.add_message(chat_id, message_id)

async def send_with_warning(message, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None, parse_mode=None):
    try:
        if hasattr(message, 'reply_text'):
            sent_message = await message.reply_text(
                f"{text}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await message.edit_text(
                f"{text}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

        await delete_message_later(context, sent_message.chat_id, sent_message.message_id)
        return sent_message
    except TelegramError as e:
        print(f"Error sending message: {e}")
        return None

async def send_photo_with_warning(message, context: ContextTypes.DEFAULT_TYPE, photo: str, caption: str, reply_markup=None, parse_mode=None):
    try:
        if hasattr(message, 'reply_photo'):
            sent_message = await message.reply_photo(
                photo=photo,
                caption=f"{caption}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await context.bot.send_photo(
                chat_id=message.chat_id,
                photo=photo,
                caption=f"{caption}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

        await delete_message_later(context, sent_message.chat_id, sent_message.message_id)
        return sent_message
    except TelegramError as e:
        print(f"Error sending photo: {e}")
        return None


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    keyboard = [
        [InlineKeyboardButton("  DOWNLOAD MOVIES", callback_data='search_movies')],
        [
            InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
            InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
            InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
        ],
        [InlineKeyboardButton("📈 Popular Movies", callback_data='popular'),
         InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
        [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
        [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_with_warning(
        update.message,
        context,
        f"👋 Hello {user_name}! Welcome to @movieshuba11_bot!\n\nClick on /start to restart or type",
        reply_markup=reply_markup
    )

async def show_start_menu(message, context: ContextTypes.DEFAULT_TYPE):
    # Get user's name from the callback query
    user_name = message._effective_user.first_name if hasattr(message, '_effective_user') else "there"
    keyboard = [
        [InlineKeyboardButton(" Download movies", callback_data='search_movies')],
        [
            InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
            InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
            InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
        ],
        [InlineKeyboardButton("📈 Popular Movies", callback_data='popular')],
        [InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
        [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
        [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_with_warning(
        message,
        context,
        f"👋 Hello {user_name}! Welcome to moviieshubb_bot!\n\nClick on /start to restart or type",
        reply_markup=reply_markup
    )



async def get_random_movies_by_genre(message, context: ContextTypes.DEFAULT_TYPE, genre_id=None):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "sort_by": "popularity.desc",
            "page": 1
        }

        if genre_id:
            params["with_genres"] = genre_id

        response = requests.get(url, params=params)
        response.raise_for_status()
        total_pages = min(response.json().get("total_pages", 1), 500)

        random_page = random.randint(1, total_pages)
        params["page"] = random_page

        response = requests.get(url, params=params)
        response.raise_for_status()

        all_movies = response.json().get("results", [])
        random_movies = random.sample(all_movies, min(5, len(all_movies)))

        response_text = "🎲 Random Movie Suggestions:\n\n"
        keyboard = []
        for i, movie in enumerate(random_movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"
            keyboard.append([InlineKeyboardButton(f"🔍 Search {movie['title']}", callback_data=f'search_specific_{movie["id"]}')])

        keyboard.extend([
            [
                InlineKeyboardButton("👻 Horror", callback_data='random_horror'),
                InlineKeyboardButton("🔪 Crime", callback_data='random_crime'),
                InlineKeyboardButton("💝 Romance", callback_data='random_romance')
            ],
            [InlineKeyboardButton("🎲 More Random", callback_data='random_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching random movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='random_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                                "Sorry, couldn't fetch random movies right now.",
                                reply_markup=reply_markup)


async def get_popular_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/movie/popular"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "🎬 Currently Popular Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching popular movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='popular')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch popular movies right now.",
                              reply_markup=reply_markup)

async def get_horror_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "with_genres": HORROR_GENRE_ID,
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "👻 Popular Horror Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton("👻 More Horror Movies", callback_data='horror_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching horror movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='horror_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch horror movies right now.",
                              reply_markup=reply_markup)

async def get_bollywood_popular_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "region": "IN",
            "with_original_language": "hi",
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "🎬  Bollywood Popular Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching Bollywood movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='bollywood_popular')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch Bollywood movies right now.",
                              reply_markup=reply_markup)


async def search_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    special_case, special_links = special_cases_manager.is_special_case(query)
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Log the search
    search_logger.log_search(user_id, user_name, "movie", query)
    try:
        tmdb_handler = TMDBAPIHandler(TMDB_API_KEY)

        # Search for movie
        results = tmdb_handler.make_request(
            "/search/movie",
            params={"query": query, "language": "en-US"}
        ).get("results", [])

        if results:
            movie = results[0]
            movie_id = movie["id"]

            # Get movie details
            movie_details = tmdb_handler.make_request(f"/movie/{movie_id}")
            providers = tmdb_handler.make_request(f"/movie/{movie_id}/watch/providers").get("results", {}).get("US",
                                                                                                               {}).get(
                "flatrate", [])

        search_url = f"{TMDB_BASE_URL}/search/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        if results:
            movie = results[0]
            movie_id = movie["id"]

            details_url = f"{TMDB_BASE_URL}/movie/{movie_id}"
            watch_providers_url = f"{TMDB_BASE_URL}/movie/{movie_id}/watch/providers"

            details_response = requests.get(details_url, params={"api_key": TMDB_API_KEY})
            providers_response = requests.get(watch_providers_url, params={"api_key": TMDB_API_KEY})

            movie_details = details_response.json()
            providers = providers_response.json().get("results", {}).get("US", {}).get("flatrate", [])

            keyboard = [
                [InlineKeyboardButton(" Search Another Movie", callback_data='search_movies')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            response_text = (
                f"*{movie_details['title']}* ({movie_details.get('release_date', '')[:4]})\n\n"
                f"Plot: {movie_details.get('overview', 'No plot available')}\n\n"
            )

            if providers:
                response_text += "Available on: " + ", ".join(p["provider_name"] for p in providers) + "\n\n"
            else:
                response_text += "Streaming information not available\n\n"

            if special_case and special_links:
                response_text += "Download Links:\n"
                for link in special_links:
                    lang_text = f" ({link['language']})" if link.get('language') else ""
                    response_text += f"• {link['url']}{lang_text}\n"
            else:
                response_text += "download link comming soon msg @balaram129"

            if movie_details.get("poster_path"):
                poster_url = f"{TMDB_IMAGE_BASE_URL}{movie_details['poster_path']}"
                await send_photo_with_warning(update.message, context, photo=poster_url, caption=response_text, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                await send_with_warning(update.message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            keyboard = [
                [InlineKeyboardButton(" Try Again", callback_data='search_movies')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(update.message, context, "No movies found matching your search.", reply_markup=reply_markup)
    except Exception as e:
        print(f"Error in movie search: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(update.message, context,
                              "Sorry, there was an error processing your request. Please try again.",
                              reply_markup=reply_markup)

async def search_by_actor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Log the search
    search_logger.log_search(user_id, user_name, "actor", query)
    try:
        search_url = f"{TMDB_BASE_URL}/search/person"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        if results:
            actor = results[0]
            actor_id = actor["id"]

            actor_details_url = f"{TMDB_BASE_URL}/person/{actor_id}"
            movies_url = f"{TMDB_BASE_URL}/person/{actor_id}/movie_credits"

            actor_details_response = requests.get(actor_details_url, params={"api_key": TMDB_API_KEY})
            movies_response = requests.get(movies_url, params={"api_key": TMDB_API_KEY})

            actor_details = actor_details_response.json()
            movies = movies_response.json().get("cast", [])

            movies_with_rating = [m for m in movies if m.get("vote_average", 0) > 0]
            sorted_movies = sorted(movies_with_rating, key=lambda x: x.get("vote_average", 0), reverse=True)

            popular_movies = [m for m in sorted_movies if m.get("vote_average", 0) >= 7][:4]
            unpopular_movies = [m for m in sorted_movies if m.get("vote_average", 0) < 7][:4]

            response_text = f"🎭 {actor['name']}\n"
            if actor_details.get("birthday"):
                response_text += f"Birthday: {actor_details['birthday']}\n"
            if actor_details.get("place_of_birth"):
                response_text += f"Birthplace: {actor_details['place_of_birth']}\n"

            response_text += "\n📈 Highly Rated Movies:\n"
            for i, movie in enumerate(popular_movies, 1):
                response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
                response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"

            response_text += "\n📉 Other Notable Movies:\n"
            for i, movie in enumerate(unpopular_movies, 1):
                response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
                response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"

            keyboard = [
                [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
                [InlineKeyboardButton(" Search Another Actor", callback_data='search_actor')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            if actor.get("profile_path"):
                actor_image_url = f"{TMDB_IMAGE_BASE_URL}{actor['profile_path']}"
                await send_photo_with_warning(
                    update.message,
                    context,
                    photo=actor_image_url,
                    caption=response_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await send_with_warning(
                    update.message,
                    context,
                    response_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
        else:
            keyboard = [
                [InlineKeyboardButton(" Try Again", callback_data='search_actor')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                update.message,
                context,
                "No actor found matching your search.",
                reply_markup=reply_markup
            )
    except Exception as e:
        print(f"Error in actor search: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='search_actor')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(
            update.message,
            context,
            "Sorry, there was an error processing your request. Please try again.",
            reply_markup=reply_markup
        )
def is_special_case(query):
    query_lower = query.lower().strip()
    for key, case in special_cases_manager.items():
        if query_lower == key.lower() or query_lower in [v.lower() for v in case["variants"]]:
            return True, case["links"]
    return False, []

async def get_genre_movies(message, context: ContextTypes.DEFAULT_TYPE, genre_id: int, genre_name: str):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "with_genres": genre_id,
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = f"🎬 Popular {genre_name} Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching {genre_name} movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data=f'genre_{genre_name.lower()}')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              f"Sorry, couldn't fetch {genre_name} movies right now.",
                              reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_name = query.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    try:
        if query.data.startswith('search_specific_'):
            movie_id = query.data.split('_')[2]
            # Get movie details from TMDB
            url = f"{TMDB_BASE_URL}/movie/{movie_id}"
            response = requests.get(url, params={"api_key": TMDB_API_KEY})
            movie = response.json()

            # Create a message with movie details
            movie_text = f"{movie['title']} ({movie.get('release_date', '')[:4]})"

            # Send a temporary message to user's private chat
            class SimulatedMessage:
                def __init__(self, chat_id, text, from_user):
                    self.chat_id = chat_id
                    self.text = text
                    self.from_user = from_user

                def reply_text(self, *args, **kwargs):
                    return query.message.reply_text(*args, **kwargs)

                def reply_photo(self, *args, **kwargs):
                    return query.message.reply_photo(*args, **kwargs)

            # Create a proper message object
            simulated_message = SimulatedMessage(
                chat_id=query.message.chat_id,
                text=movie['title'],
                from_user=query.from_user
            )

            # Create a proper update object
            class SimulatedUpdate:
                def __init__(self, message):
                    self.message = message

            simulated_update = SimulatedUpdate(simulated_message)

            # Perform the search
            await search_movie(simulated_update, context)
            return
        if query.data == 'genre_horror':
            await get_genre_movies(query.message, context, GENRE_IDS['horror'], "Horror")
        elif query.data == 'genre_romance':
            await get_genre_movies(query.message, context, GENRE_IDS['romance'], "Romance")
        elif query.data == 'genre_crime':
            await get_genre_movies(query.message, context, GENRE_IDS['crime'], "Crime")
        elif query.data == 'random_movies':
            await get_random_movies_by_genre(query.message, context)
        if query.data == 'random_movies':
            await get_random_movies_by_genre(query.message, context)
        elif query.data == 'random_horror':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['horror'])
        elif query.data == 'random_crime':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['crime'])
        elif query.data == 'random_romance':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['romance'])
        elif query.data == 'horror_movies':
            await get_horror_movies(query.message, context)
        elif query.data == 'search_movies':
            USER_CONTEXT[query.message.chat_id] = 'movie'
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "🔍 Just type the name of any movie you want to search for!",
                reply_markup=reply_markup
            )
        elif query.data == 'search_actor':
            USER_CONTEXT[query.message.chat_id] = 'actor'
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "🎭 Just type the name of any actor to see their movies!",
                reply_markup=reply_markup
            )
        elif query.data == 'help':
            help_text = ("📖 How to use this bot:\n\n"
                        "1. Simply type any movie name\n"
                        "2. Or type any actor name to find their movies\n"
                        "3. I'll show you the details\n"
                        "4. Check out popular movies in both Hollywood and Bollywood\n"
                        "5. Try our random movie suggestions by genre!\n"
                        "Need more help? Just type /start to see the main menu again! or msg @balaram129")
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                help_text,
                reply_markup=reply_markup
            )
        elif query.data == 'popular':
            await get_popular_movies(query.message, context)
        elif query.data == 'bollywood_popular':
            await get_bollywood_popular_movies(query.message, context)
        elif query.data == 'start_menu':
            keyboard = [
                [InlineKeyboardButton("🔍 Download movies", callback_data='search_movies'),
                 InlineKeyboardButton("👻 Horror Movies", callback_data='horror_movies')],
                [
                    InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
                    InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
                    InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
                ],
                [InlineKeyboardButton("📈 Popular Movies", callback_data='popular')],
                [InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
                [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
                [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
                [InlineKeyboardButton("❓ Help", callback_data='help')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "👋 Welcome to moviieshubb_bot!\n\nClick on /start to restart or type",
                reply_markup=reply_markup
            )

    except Exception as e:
        print(f"Error in button callback: {e}")
        keyboard = [
            [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(
            query.message,
            context,
            "Sorry, there was an error processing your request. Please try again.",
            reply_markup=reply_markup
        )

async def handle_user_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_context = USER_CONTEXT.get(update.message.chat_id, "movie")
    if user_context == "actor":
        await search_by_actor(update, context)
    else:
        await search_movie(update, context)

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_message_later(context, update.message.chat_id, update.message.message_id)
    await handle_user_query(update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Exception while handling an update: {context.error}")
    if isinstance(context.error, Conflict):
        print("Bot instance already running. Exiting...")
        sys.exit(1)
    elif isinstance(context.error, NetworkError):
        print("Network error occurred. Waiting before retry...")
        await asyncio.sleep(1)
    else:
        print(f"Unexpected error: {context.error}")


def main():
    try:
        application = (
            Application.builder()
            .token(TELEGRAM_TOKEN)
            .build()
        )

        # Add existing handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CallbackQueryHandler(button_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))
        application.add_handler(CommandHandler("viewsearches", view_searches_command))

        # Add error handler
        application.add_error_handler(error_handler)

        # Set up the cleanup job to run every 10 seconds
        job_queue = application.job_queue
        job_queue.run_repeating(cleanup_job, interval=10, first=0)

        # Add the inactive user check job (runs every 6 hours)
        job_queue.run_repeating(check_inactive_users, interval=21600, first=21600)

        # Update stastics more frequently (every 5 minutes)
        job_queue.run_repeating(update_stastics_job, interval=300, first=0)

        # Initial statistics update
        print("Performing initial statistics update...")
        stats = SearchStatistics()
        stats.update_stastics_file()
        print("Initial statistics update completed")

        # Start the bot
        print("Starting bot...")
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

    except Exception as e:
        print(f"Error starting bot: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

# Test the logger
logger = SearchLogger()
logger.log_search(123456, "TestUser", "movie", "Avatar")

# Check recent searches
recent = logger.get_recent_searches()
print("Recent searches:", recent)import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import Conflict, NetworkError, TelegramError
import nest_asyncio
import sys
import random
from typing import Optional, Dict
from datetime import datetime, timedelta
import pickle
from special_cases_managerss import SpecialCasesManager
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import json
from datetime import datetime
from pathlib import Path


class SearchLogger:
    def __init__(self, log_file="search_logs.json"):
        self.log_file = log_file
        self.ensure_log_file_exists()

    def ensure_log_file_exists(self):
        # Create the file with an empty list if it doesn't exist or is empty
        if not Path(self.log_file).exists() or Path(self.log_file).stat().st_size == 0:
            with open(self.log_file, 'w') as f:
                json.dump([], f)

    def log_search(self, user_id: int, user_name: str, search_type: str, search_query: str):
        try:
            # First ensure the file exists and has valid JSON
            self.ensure_log_file_exists()

            # Read existing logs
            try:
                with open(self.log_file, 'r') as f:
                    logs = json.load(f)
            except json.JSONDecodeError:
                # If there's an error reading the JSON, start with an empty list
                logs = []

            # Create new log entry
            log_entry = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "user_id": user_id,
                "user_name": user_name,
                "search_type": search_type,
                "search_query": search_query
            }

            # Add new entry
            logs.append(log_entry)

            # Write back to file
            with open(self.log_file, 'w') as f:
                json.dump(logs, f, indent=2)

        except Exception as e:
            print(f"Error logging search: {e}")

    def get_recent_searches(self, limit: int = 100):
        try:
            # First ensure the file exists and has valid JSON
            self.ensure_log_file_exists()

            with open(self.log_file, 'r') as f:
                try:
                    logs = json.load(f)
                except json.JSONDecodeError:
                    return []
            return logs[-limit:]
        except Exception as e:
            print(f"Error getting recent searches: {e}")
            return []


# Create an instance of the logger
search_logger = SearchLogger()


# After your other global variables
special_cases_manager = SpecialCasesManager()

# Initialize some cases if you want (optional)
special_cases_manager.add_case(
    "pushpa 2",
    ["pushpa2", "pushpa-2", "pushpa2therule", "pushpa 2 the rule"],
    [
        {"url": "https://example4.com", "language": "Hindi"},
        {"url": "https://example5.com", "language": "Telugu"}
    ]
)

special_cases_manager.add_case(
    "venom",
    ["venom", "venom1", "venom2"],
    [
        {"url": "https://www.udlinks.com/3I1l", "language": "hindi"}
    ]
)




nest_asyncio.apply()

TELEGRAM_TOKEN = "7883754025:AAHUDU-_EM4QYome14k_28PQbPTWsl_9w6s"
TMDB_API_KEY = "c3b8704a4df65146c194940351efa9a2"
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
DELETE_TIMEOUT = 420  # 7 minutes in seconds
DISCLAIMER = "⚠️ This message will be deleted in 7 minutes"
HORROR_GENRE_ID = 27  # TMDB's genre ID for horror movies



USER_CONTEXT = {}

GENRE_IDS = {
    'horror': 27,
    'crime': 80,
    'romance': 10749
}


class TMDBAPIHandler:
    def __init__(self, api_key, base_url="https://api.themoviedb.org/3"):
        self.api_key = api_key
        self.base_url = base_url
        self.session = self._create_session()

    def _create_session(self):
        session = requests.Session()

        # Configure retry strategy
        retries = Retry(
            total=5,  # Total number of retries
            backoff_factor=0.5,  # Wait 0.5, 1, 2, 4, 8 seconds between retries
            status_forcelist=[500, 502, 503, 504, 408, 429]  # HTTP status codes to retry on
        )

        # Add retry adapter to session
        adapter = HTTPAdapter(max_retries=retries)
        session.mount('http://', adapter)
        session.mount('https://', adapter)

        return session

    def make_request(self, endpoint, params=None):
        if params is None:
            params = {}

        # Always include API key
        params['api_key'] = self.api_key

        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                response = self.session.get(
                    f"{self.base_url}{endpoint}",
                    params=params,
                    timeout=10  # 10 seconds timeout
                )
                response.raise_for_status()
                return response.json()

            except requests.exceptions.ConnectionError as e:
                if attempt == max_attempts - 1:
                    raise Exception("Unable to connect to TMDB API. Please check your internet connection.") from e
                time.sleep(2 ** attempt)  # Exponential backoff

            except requests.exceptions.Timeout as e:
                if attempt == max_attempts - 1:
                    raise Exception("TMDB API request timed out. Please try again later.") from e
                time.sleep(2 ** attempt)

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:  # Rate limit exceeded
                    retry_after = int(e.response.headers.get('Retry-After', 5))
                    time.sleep(retry_after)
                    continue
                raise Exception(f"TMDB API error: {e.response.status_code}") from e


LAST_ACTIVITY_FILE = "user_activity.pkl"
INACTIVITY_THRESHOLD = timedelta(hours=78)


class SearchStatistics:
    def __init__(self, log_file="search_logs.json", stats_file="stastics.txt"):
        self.log_file = log_file
        self.stats_file = stats_file
        self.search_logger = SearchLogger(log_file)
        # Ensure stastics file exists
        self.update_stastics_file()
        print(f"SearchStatistics initialized. Stats file: {stats_file}")

    def _load_searches(self):
        """Load searches from the log file"""
        try:
            with open(self.log_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def get_most_searched(self, days=None):
        """Get most searched queries within specified days"""
        searches = self._load_searches()
        if not searches:
            return []

        # Filter by date if days is specified
        if days:
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            searches = [s for s in searches if s['timestamp'][:10] >= cutoff_date]

        # Count search queries
        query_counts = {}
        for search in searches:
            query = search['search_query'].lower()
            query_counts[query] = query_counts.get(query, 0) + 1

        # Sort by count and return top 10
        return sorted(query_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    def get_user_search_history(self, limit=50):
        """Get recent user search history"""
        searches = self._load_searches()
        return searches[-limit:] if searches else []

    def update_stastics_file(self):  # Changed method name to match file name
        try:
            print(f"Updating stastics file at {datetime.now()}")

            # Check if log file exists and has data
            if not Path(self.log_file).exists():
                print(f"Log file {self.log_file} does not exist!")
                return

            # Load searches
            searches = self._load_searches()
            if not searches:
                print("No search data found in logs")
                stats_text = "No search data available yet.\nLast Updated: " + datetime.now().strftime(
                    '%Y-%m-%d %H:%M:%S')
            else:
                # Get statistics for different time periods
                all_time = self.get_most_searched()
                today = self.get_most_searched(days=1)
                week = self.get_most_searched(days=7)
                year = self.get_most_searched(days=365)
                user_history = self.get_user_search_history(limit=50)

                stats_text = self._format_stastics(all_time, today, week, year, user_history)  # Changed method name

            # Write to stastics file
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                f.write(stats_text)

            print(f"Stastics file updated successfully at {datetime.now()}")

            # Debug: Read and print file contents
            with open(self.stats_file, 'r', encoding='utf-8') as f:
                content = f.read()
            print(f"Stastics file size: {len(content)} bytes")

        except Exception as e:
            print(f"Error updating stastics file: {e}")
            import traceback
            traceback.print_exc()

    def _format_stastics(self, all_time, today, week, year, user_history):  # Changed method name
        stats_text = "Movie Search Stastics\n"  # Changed heading
        stats_text += "=" * 50 + "\n\n"

        # Add section for each time period
        sections = [
            ("All-Time Most Searched Movies:", all_time),
            ("Today's Most Searched Movies:", today),
            ("This Week's Most Searched Movies:", week),
            ("This Year's Most Searched Movies:", year)
        ]

        for title, data in sections:
            stats_text += f"{title}\n"
            if data:
                stats_text += "\n".join(f"{i + 1}. {movie} ({count} searches)"
                                      for i, (movie, count) in enumerate(data))
            else:
                stats_text += "No searches in this period"
            stats_text += "\n\n"

        # Add user history section
        stats_text += "Recent User Search History:\n"
        stats_text += "=" * 50 + "\n"
        if user_history:
            for search in user_history:
                stats_text += f"\nTime: {search['timestamp']}\n"
                stats_text += f"User: {search['user_name']} (ID: {search['user_id']})\n"
                stats_text += f"Search Type: {search['search_type']}\n"
                stats_text += f"Query: {search['search_query']}\n"
                stats_text += "-" * 30 + "\n"
        else:
            stats_text += "\nNo user search history available yet\n"

        stats_text += f"\nLast Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        return stats_text

# Modify the update_statistics_job to include error handling and logging
async def update_stastics_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        print(f"Starting stastics update job at {datetime.now()}")
        stats = SearchStatistics()
        stats.update_stastics_file()
        print(f"Completed stastics update job at {datetime.now()}")
    except Exception as e:
        print(f"Error in stastics update job: {e}")
        import traceback
        traceback.print_exc()

async def view_searches_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only allow yourself to see the searches
    if update.message.from_user.id == 6822829183:  # Replace with your Telegram ID
        recent_searches = search_logger.get_recent_searches(limit=10)  # Get last 10 searches

        message = "Recent Searches:\n\n"
        for search in recent_searches:
            message += f"👤 User: {search['user_name']}\n"
            message += f"🔍 Query: {search['search_query']}\n"
            message += f"⏰ Time: {search['timestamp']}\n"
            message += f"Type: {search['search_type']}\n\n"

        await update.message.reply_text(message)
    else:
        await update.message.reply_text("You don't have permission to use this command.")


# Add this to your command handlers

class UserActivityManager:
    def __init__(self):
        self.user_activity = {}
        self.load_activity()

    def load_activity(self):
        if Path(LAST_ACTIVITY_FILE).exists():
            try:
                with open(LAST_ACTIVITY_FILE, 'rb') as f:
                    self.user_activity = pickle.load(f)
            except Exception as e:
                print(f"Error loading user activity: {e}")
                self.user_activity = {}

    def save_activity(self):
        try:
            with open(LAST_ACTIVITY_FILE, 'wb') as f:
                pickle.dump(self.user_activity, f)
        except Exception as e:
            print(f"Error saving user activity: {e}")

    def update_user_activity(self, user_id: int, user_name: str):
        self.user_activity[user_id] = {
            'last_active': datetime.now(),
            'name': user_name
        }
        self.save_activity()

    def get_inactive_users(self):
        current_time = datetime.now()
        inactive_users = []

        for user_id, data in self.user_activity.items():
            if (current_time - data['last_active']) >= INACTIVITY_THRESHOLD:
                inactive_users.append({
                    'user_id': user_id,
                    'name': data['name'],
                    'last_active': data['last_active']
                })

        return inactive_users


# Create global instance
activity_manager = UserActivityManager()


# Modify the handle_user_message function to track activity
async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    await delete_message_later(context, update.message.chat_id, update.message.message_id)
    await handle_user_query(update, context)


# Add a new function to check for inactive users
async def check_inactive_users(context: ContextTypes.DEFAULT_TYPE):
    inactive_users = activity_manager.get_inactive_users()

    for user in inactive_users:
        try:
            message = f"Hey {user['name']} 👋,\n\nI am missing you dear! 💫\nIt's been a while since we last chatted. Come back and discover some amazing movies! 🎬"

            await context.bot.send_message(
                chat_id=user['user_id'],
                text=message,
                parse_mode='Markdown'
            )

            # Update the last activity to prevent spam
            activity_manager.update_user_activity(user['user_id'], user['name'])

        except Exception as e:
            print(f"Error sending reminder to user {user['user_id']}: {e}")

class MessageTracker:
    def __init__(self):
        self.messages: Dict[int, Dict[int, datetime]] = {}

    async def add_message(self, chat_id: int, message_id: int):
        if chat_id not in self.messages:
            self.messages[chat_id] = {}
        self.messages[chat_id][message_id] = datetime.now() + timedelta(seconds=DELETE_TIMEOUT)

    async def cleanup_messages(self, context: ContextTypes.DEFAULT_TYPE):
        current_time = datetime.now()
        for chat_id in list(self.messages.keys()):
            for message_id, expiry_time in list(self.messages[chat_id].items()):
                if current_time >= expiry_time:
                    try:
                        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                    except TelegramError:
                        pass  # Message might already be deleted
                    finally:
                        del self.messages[chat_id][message_id]
            if not self.messages[chat_id]:
                del self.messages[chat_id]

message_tracker = MessageTracker()

async def cleanup_job(context: ContextTypes.DEFAULT_TYPE):
    await message_tracker.cleanup_messages(context)

async def delete_message_later(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int):
    await message_tracker.add_message(chat_id, message_id)

async def send_with_warning(message, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None, parse_mode=None):
    try:
        if hasattr(message, 'reply_text'):
            sent_message = await message.reply_text(
                f"{text}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await message.edit_text(
                f"{text}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

        await delete_message_later(context, sent_message.chat_id, sent_message.message_id)
        return sent_message
    except TelegramError as e:
        print(f"Error sending message: {e}")
        return None

async def send_photo_with_warning(message, context: ContextTypes.DEFAULT_TYPE, photo: str, caption: str, reply_markup=None, parse_mode=None):
    try:
        if hasattr(message, 'reply_photo'):
            sent_message = await message.reply_photo(
                photo=photo,
                caption=f"{caption}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await context.bot.send_photo(
                chat_id=message.chat_id,
                photo=photo,
                caption=f"{caption}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

        await delete_message_later(context, sent_message.chat_id, sent_message.message_id)
        return sent_message
    except TelegramError as e:
        print(f"Error sending photo: {e}")
        return None


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    keyboard = [
        [InlineKeyboardButton("  DOWNLOAD MOVIES", callback_data='search_movies')],
        [
            InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
            InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
            InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
        ],
        [InlineKeyboardButton("📈 Popular Movies", callback_data='popular'),
         InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
        [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
        [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_with_warning(
        update.message,
        context,
        f"👋 Hello {user_name}! Welcome to @movieshuba11_bot!\n\nClick on /start to restart or type",
        reply_markup=reply_markup
    )

async def show_start_menu(message, context: ContextTypes.DEFAULT_TYPE):
    # Get user's name from the callback query
    user_name = message._effective_user.first_name if hasattr(message, '_effective_user') else "there"
    keyboard = [
        [InlineKeyboardButton(" Download movies", callback_data='search_movies')],
        [
            InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
            InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
            InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
        ],
        [InlineKeyboardButton("📈 Popular Movies", callback_data='popular')],
        [InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
        [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
        [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_with_warning(
        message,
        context,
        f"👋 Hello {user_name}! Welcome to moviieshubb_bot!\n\nClick on /start to restart or type",
        reply_markup=reply_markup
    )



async def get_random_movies_by_genre(message, context: ContextTypes.DEFAULT_TYPE, genre_id=None):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "sort_by": "popularity.desc",
            "page": 1
        }

        if genre_id:
            params["with_genres"] = genre_id

        response = requests.get(url, params=params)
        response.raise_for_status()
        total_pages = min(response.json().get("total_pages", 1), 500)

        random_page = random.randint(1, total_pages)
        params["page"] = random_page

        response = requests.get(url, params=params)
        response.raise_for_status()

        all_movies = response.json().get("results", [])
        random_movies = random.sample(all_movies, min(5, len(all_movies)))

        response_text = "🎲 Random Movie Suggestions:\n\n"
        keyboard = []
        for i, movie in enumerate(random_movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"
            keyboard.append([InlineKeyboardButton(f"🔍 Search {movie['title']}", callback_data=f'search_specific_{movie["id"]}')])

        keyboard.extend([
            [
                InlineKeyboardButton("👻 Horror", callback_data='random_horror'),
                InlineKeyboardButton("🔪 Crime", callback_data='random_crime'),
                InlineKeyboardButton("💝 Romance", callback_data='random_romance')
            ],
            [InlineKeyboardButton("🎲 More Random", callback_data='random_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching random movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='random_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                                "Sorry, couldn't fetch random movies right now.",
                                reply_markup=reply_markup)


async def get_popular_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/movie/popular"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "🎬 Currently Popular Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching popular movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='popular')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch popular movies right now.",
                              reply_markup=reply_markup)

async def get_horror_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "with_genres": HORROR_GENRE_ID,
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "👻 Popular Horror Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton("👻 More Horror Movies", callback_data='horror_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching horror movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='horror_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch horror movies right now.",
                              reply_markup=reply_markup)

async def get_bollywood_popular_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "region": "IN",
            "with_original_language": "hi",
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "🎬  Bollywood Popular Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching Bollywood movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='bollywood_popular')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch Bollywood movies right now.",
                              reply_markup=reply_markup)


async def search_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    special_case, special_links = special_cases_manager.is_special_case(query)
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Log the search
    search_logger.log_search(user_id, user_name, "movie", query)
    try:
        tmdb_handler = TMDBAPIHandler(TMDB_API_KEY)

        # Search for movie
        results = tmdb_handler.make_request(
            "/search/movie",
            params={"query": query, "language": "en-US"}
        ).get("results", [])

        if results:
            movie = results[0]
            movie_id = movie["id"]

            # Get movie details
            movie_details = tmdb_handler.make_request(f"/movie/{movie_id}")
            providers = tmdb_handler.make_request(f"/movie/{movie_id}/watch/providers").get("results", {}).get("US",
                                                                                                               {}).get(
                "flatrate", [])

        search_url = f"{TMDB_BASE_URL}/search/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        if results:
            movie = results[0]
            movie_id = movie["id"]

            details_url = f"{TMDB_BASE_URL}/movie/{movie_id}"
            watch_providers_url = f"{TMDB_BASE_URL}/movie/{movie_id}/watch/providers"

            details_response = requests.get(details_url, params={"api_key": TMDB_API_KEY})
            providers_response = requests.get(watch_providers_url, params={"api_key": TMDB_API_KEY})

            movie_details = details_response.json()
            providers = providers_response.json().get("results", {}).get("US", {}).get("flatrate", [])

            keyboard = [
                [InlineKeyboardButton(" Search Another Movie", callback_data='search_movies')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            response_text = (
                f"*{movie_details['title']}* ({movie_details.get('release_date', '')[:4]})\n\n"
                f"Plot: {movie_details.get('overview', 'No plot available')}\n\n"
            )

            if providers:
                response_text += "Available on: " + ", ".join(p["provider_name"] for p in providers) + "\n\n"
            else:
                response_text += "Streaming information not available\n\n"

            if special_case and special_links:
                response_text += "Download Links:\n"
                for link in special_links:
                    lang_text = f" ({link['language']})" if link.get('language') else ""
                    response_text += f"• {link['url']}{lang_text}\n"
            else:
                response_text += "download link comming soon msg @balaram129"

            if movie_details.get("poster_path"):
                poster_url = f"{TMDB_IMAGE_BASE_URL}{movie_details['poster_path']}"
                await send_photo_with_warning(update.message, context, photo=poster_url, caption=response_text, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                await send_with_warning(update.message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            keyboard = [
                [InlineKeyboardButton(" Try Again", callback_data='search_movies')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(update.message, context, "No movies found matching your search.", reply_markup=reply_markup)
    except Exception as e:
        print(f"Error in movie search: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(update.message, context,
                              "Sorry, there was an error processing your request. Please try again.",
                              reply_markup=reply_markup)

async def search_by_actor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Log the search
    search_logger.log_search(user_id, user_name, "actor", query)
    try:
        search_url = f"{TMDB_BASE_URL}/search/person"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        if results:
            actor = results[0]
            actor_id = actor["id"]

            actor_details_url = f"{TMDB_BASE_URL}/person/{actor_id}"
            movies_url = f"{TMDB_BASE_URL}/person/{actor_id}/movie_credits"

            actor_details_response = requests.get(actor_details_url, params={"api_key": TMDB_API_KEY})
            movies_response = requests.get(movies_url, params={"api_key": TMDB_API_KEY})

            actor_details = actor_details_response.json()
            movies = movies_response.json().get("cast", [])

            movies_with_rating = [m for m in movies if m.get("vote_average", 0) > 0]
            sorted_movies = sorted(movies_with_rating, key=lambda x: x.get("vote_average", 0), reverse=True)

            popular_movies = [m for m in sorted_movies if m.get("vote_average", 0) >= 7][:4]
            unpopular_movies = [m for m in sorted_movies if m.get("vote_average", 0) < 7][:4]

            response_text = f"🎭 {actor['name']}\n"
            if actor_details.get("birthday"):
                response_text += f"Birthday: {actor_details['birthday']}\n"
            if actor_details.get("place_of_birth"):
                response_text += f"Birthplace: {actor_details['place_of_birth']}\n"

            response_text += "\n📈 Highly Rated Movies:\n"
            for i, movie in enumerate(popular_movies, 1):
                response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
                response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"

            response_text += "\n📉 Other Notable Movies:\n"
            for i, movie in enumerate(unpopular_movies, 1):
                response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
                response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"

            keyboard = [
                [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
                [InlineKeyboardButton(" Search Another Actor", callback_data='search_actor')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            if actor.get("profile_path"):
                actor_image_url = f"{TMDB_IMAGE_BASE_URL}{actor['profile_path']}"
                await send_photo_with_warning(
                    update.message,
                    context,
                    photo=actor_image_url,
                    caption=response_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await send_with_warning(
                    update.message,
                    context,
                    response_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
        else:
            keyboard = [
                [InlineKeyboardButton(" Try Again", callback_data='search_actor')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                update.message,
                context,
                "No actor found matching your search.",
                reply_markup=reply_markup
            )
    except Exception as e:
        print(f"Error in actor search: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='search_actor')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(
            update.message,
            context,
            "Sorry, there was an error processing your request. Please try again.",
            reply_markup=reply_markup
        )
def is_special_case(query):
    query_lower = query.lower().strip()
    for key, case in special_cases_manager.items():
        if query_lower == key.lower() or query_lower in [v.lower() for v in case["variants"]]:
            return True, case["links"]
    return False, []

async def get_genre_movies(message, context: ContextTypes.DEFAULT_TYPE, genre_id: int, genre_name: str):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "with_genres": genre_id,
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = f"🎬 Popular {genre_name} Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching {genre_name} movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data=f'genre_{genre_name.lower()}')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              f"Sorry, couldn't fetch {genre_name} movies right now.",
                              reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_name = query.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    try:
        if query.data.startswith('search_specific_'):
            movie_id = query.data.split('_')[2]
            # Get movie details from TMDB
            url = f"{TMDB_BASE_URL}/movie/{movie_id}"
            response = requests.get(url, params={"api_key": TMDB_API_KEY})
            movie = response.json()

            # Create a message with movie details
            movie_text = f"{movie['title']} ({movie.get('release_date', '')[:4]})"

            # Send a temporary message to user's private chat
            class SimulatedMessage:
                def __init__(self, chat_id, text, from_user):
                    self.chat_id = chat_id
                    self.text = text
                    self.from_user = from_user

                def reply_text(self, *args, **kwargs):
                    return query.message.reply_text(*args, **kwargs)

                def reply_photo(self, *args, **kwargs):
                    return query.message.reply_photo(*args, **kwargs)

            # Create a proper message object
            simulated_message = SimulatedMessage(
                chat_id=query.message.chat_id,
                text=movie['title'],
                from_user=query.from_user
            )

            # Create a proper update object
            class SimulatedUpdate:
                def __init__(self, message):
                    self.message = message

            simulated_update = SimulatedUpdate(simulated_message)

            # Perform the search
            await search_movie(simulated_update, context)
            return
        if query.data == 'genre_horror':
            await get_genre_movies(query.message, context, GENRE_IDS['horror'], "Horror")
        elif query.data == 'genre_romance':
            await get_genre_movies(query.message, context, GENRE_IDS['romance'], "Romance")
        elif query.data == 'genre_crime':
            await get_genre_movies(query.message, context, GENRE_IDS['crime'], "Crime")
        elif query.data == 'random_movies':
            await get_random_movies_by_genre(query.message, context)
        if query.data == 'random_movies':
            await get_random_movies_by_genre(query.message, context)
        elif query.data == 'random_horror':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['horror'])
        elif query.data == 'random_crime':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['crime'])
        elif query.data == 'random_romance':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['romance'])
        elif query.data == 'horror_movies':
            await get_horror_movies(query.message, context)
        elif query.data == 'search_movies':
            USER_CONTEXT[query.message.chat_id] = 'movie'
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "🔍 Just type the name of any movie you want to search for!",
                reply_markup=reply_markup
            )
        elif query.data == 'search_actor':
            USER_CONTEXT[query.message.chat_id] = 'actor'
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "🎭 Just type the name of any actor to see their movies!",
                reply_markup=reply_markup
            )
        elif query.data == 'help':
            help_text = ("📖 How to use this bot:\n\n"
                        "1. Simply type any movie name\n"
                        "2. Or type any actor name to find their movies\n"
                        "3. I'll show you the details\n"
                        "4. Check out popular movies in both Hollywood and Bollywood\n"
                        "5. Try our random movie suggestions by genre!\n"
                        "Need more help? Just type /start to see the main menu again! or msg @balaram129")
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                help_text,
                reply_markup=reply_markup
            )
        elif query.data == 'popular':
            await get_popular_movies(query.message, context)
        elif query.data == 'bollywood_popular':
            await get_bollywood_popular_movies(query.message, context)
        elif query.data == 'start_menu':
            keyboard = [
                [InlineKeyboardButton("🔍 Download movies", callback_data='search_movies'),
                 InlineKeyboardButton("👻 Horror Movies", callback_data='horror_movies')],
                [
                    InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
                    InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
                    InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
                ],
                [InlineKeyboardButton("📈 Popular Movies", callback_data='popular')],
                [InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
                [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
                [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
                [InlineKeyboardButton("❓ Help", callback_data='help')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "👋 Welcome to moviieshubb_bot!\n\nClick on /start to restart or type",
                reply_markup=reply_markup
            )

    except Exception as e:
        print(f"Error in button callback: {e}")
        keyboard = [
            [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(
            query.message,
            context,
            "Sorry, there was an error processing your request. Please try again.",
            reply_markup=reply_markup
        )

async def handle_user_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_context = USER_CONTEXT.get(update.message.chat_id, "movie")
    if user_context == "actor":
        await search_by_actor(update, context)
    else:
        await search_movie(update, context)

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_message_later(context, update.message.chat_id, update.message.message_id)
    await handle_user_query(update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Exception while handling an update: {context.error}")
    if isinstance(context.error, Conflict):
        print("Bot instance already running. Exiting...")
        sys.exit(1)
    elif isinstance(context.error, NetworkError):
        print("Network error occurred. Waiting before retry...")
        await asyncio.sleep(1)
    else:
        print(f"Unexpected error: {context.error}")


def main():
    try:
        application = (
            Application.builder()
            .token(TELEGRAM_TOKEN)
            .build()
        )

        # Add existing handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CallbackQueryHandler(button_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))
        application.add_handler(CommandHandler("viewsearches", view_searches_command))

        # Add error handler
        application.add_error_handler(error_handler)

        # Set up the cleanup job to run every 10 seconds
        job_queue = application.job_queue
        job_queue.run_repeating(cleanup_job, interval=10, first=0)

        # Add the inactive user check job (runs every 6 hours)
        job_queue.run_repeating(check_inactive_users, interval=21600, first=21600)

        # Update stastics more frequently (every 5 minutes)
        job_queue.run_repeating(update_stastics_job, interval=300, first=0)

        # Initial statistics update
        print("Performing initial statistics update...")
        stats = SearchStatistics()
        stats.update_stastics_file()
        print("Initial statistics update completed")

        # Start the bot
        print("Starting bot...")
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

    except Exception as e:
        print(f"Error starting bot: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

# Test the logger
logger = SearchLogger()
logger.log_search(123456, "TestUser", "movie", "Avatar")

# Check recent searches
recent = logger.get_recent_searches()
print("Recent searches:", recent)import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import Conflict, NetworkError, TelegramError
import nest_asyncio
import sys
import random
from typing import Optional, Dict
from datetime import datetime, timedelta
import pickle
from special_cases_managerss import SpecialCasesManager
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import json
from datetime import datetime
from pathlib import Path


class SearchLogger:
    def __init__(self, log_file="search_logs.json"):
        self.log_file = log_file
        self.ensure_log_file_exists()

    def ensure_log_file_exists(self):
        # Create the file with an empty list if it doesn't exist or is empty
        if not Path(self.log_file).exists() or Path(self.log_file).stat().st_size == 0:
            with open(self.log_file, 'w') as f:
                json.dump([], f)

    def log_search(self, user_id: int, user_name: str, search_type: str, search_query: str):
        try:
            # First ensure the file exists and has valid JSON
            self.ensure_log_file_exists()

            # Read existing logs
            try:
                with open(self.log_file, 'r') as f:
                    logs = json.load(f)
            except json.JSONDecodeError:
                # If there's an error reading the JSON, start with an empty list
                logs = []

            # Create new log entry
            log_entry = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "user_id": user_id,
                "user_name": user_name,
                "search_type": search_type,
                "search_query": search_query
            }

            # Add new entry
            logs.append(log_entry)

            # Write back to file
            with open(self.log_file, 'w') as f:
                json.dump(logs, f, indent=2)

        except Exception as e:
            print(f"Error logging search: {e}")

    def get_recent_searches(self, limit: int = 100):
        try:
            # First ensure the file exists and has valid JSON
            self.ensure_log_file_exists()

            with open(self.log_file, 'r') as f:
                try:
                    logs = json.load(f)
                except json.JSONDecodeError:
                    return []
            return logs[-limit:]
        except Exception as e:
            print(f"Error getting recent searches: {e}")
            return []


# Create an instance of the logger
search_logger = SearchLogger()


# After your other global variables
special_cases_manager = SpecialCasesManager()

# Initialize some cases if you want (optional)
special_cases_manager.add_case(
    "pushpa 2",
    ["pushpa2", "pushpa-2", "pushpa2therule", "pushpa 2 the rule"],
    [
        {"url": "https://example4.com", "language": "Hindi"},
        {"url": "https://example5.com", "language": "Telugu"}
    ]
)

special_cases_manager.add_case(
    "venom",
    ["venom", "venom1", "venom2"],
    [
        {"url": "https://www.udlinks.com/3I1l", "language": "hindi"}
    ]
)




nest_asyncio.apply()

TELEGRAM_TOKEN = "7883754025:AAHUDU-_EM4QYome14k_28PQbPTWsl_9w6s"
TMDB_API_KEY = "c3b8704a4df65146c194940351efa9a2"
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
DELETE_TIMEOUT = 420  # 7 minutes in seconds
DISCLAIMER = "⚠️ This message will be deleted in 7 minutes"
HORROR_GENRE_ID = 27  # TMDB's genre ID for horror movies



USER_CONTEXT = {}

GENRE_IDS = {
    'horror': 27,
    'crime': 80,
    'romance': 10749
}


class TMDBAPIHandler:
    def __init__(self, api_key, base_url="https://api.themoviedb.org/3"):
        self.api_key = api_key
        self.base_url = base_url
        self.session = self._create_session()

    def _create_session(self):
        session = requests.Session()

        # Configure retry strategy
        retries = Retry(
            total=5,  # Total number of retries
            backoff_factor=0.5,  # Wait 0.5, 1, 2, 4, 8 seconds between retries
            status_forcelist=[500, 502, 503, 504, 408, 429]  # HTTP status codes to retry on
        )

        # Add retry adapter to session
        adapter = HTTPAdapter(max_retries=retries)
        session.mount('http://', adapter)
        session.mount('https://', adapter)

        return session

    def make_request(self, endpoint, params=None):
        if params is None:
            params = {}

        # Always include API key
        params['api_key'] = self.api_key

        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                response = self.session.get(
                    f"{self.base_url}{endpoint}",
                    params=params,
                    timeout=10  # 10 seconds timeout
                )
                response.raise_for_status()
                return response.json()

            except requests.exceptions.ConnectionError as e:
                if attempt == max_attempts - 1:
                    raise Exception("Unable to connect to TMDB API. Please check your internet connection.") from e
                time.sleep(2 ** attempt)  # Exponential backoff

            except requests.exceptions.Timeout as e:
                if attempt == max_attempts - 1:
                    raise Exception("TMDB API request timed out. Please try again later.") from e
                time.sleep(2 ** attempt)

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:  # Rate limit exceeded
                    retry_after = int(e.response.headers.get('Retry-After', 5))
                    time.sleep(retry_after)
                    continue
                raise Exception(f"TMDB API error: {e.response.status_code}") from e


LAST_ACTIVITY_FILE = "user_activity.pkl"
INACTIVITY_THRESHOLD = timedelta(hours=78)


class SearchStatistics:
    def __init__(self, log_file="search_logs.json", stats_file="stastics.txt"):
        self.log_file = log_file
        self.stats_file = stats_file
        self.search_logger = SearchLogger(log_file)
        # Ensure stastics file exists
        self.update_stastics_file()
        print(f"SearchStatistics initialized. Stats file: {stats_file}")

    def _load_searches(self):
        """Load searches from the log file"""
        try:
            with open(self.log_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def get_most_searched(self, days=None):
        """Get most searched queries within specified days"""
        searches = self._load_searches()
        if not searches:
            return []

        # Filter by date if days is specified
        if days:
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            searches = [s for s in searches if s['timestamp'][:10] >= cutoff_date]

        # Count search queries
        query_counts = {}
        for search in searches:
            query = search['search_query'].lower()
            query_counts[query] = query_counts.get(query, 0) + 1

        # Sort by count and return top 10
        return sorted(query_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    def get_user_search_history(self, limit=50):
        """Get recent user search history"""
        searches = self._load_searches()
        return searches[-limit:] if searches else []

    def update_stastics_file(self):  # Changed method name to match file name
        try:
            print(f"Updating stastics file at {datetime.now()}")

            # Check if log file exists and has data
            if not Path(self.log_file).exists():
                print(f"Log file {self.log_file} does not exist!")
                return

            # Load searches
            searches = self._load_searches()
            if not searches:
                print("No search data found in logs")
                stats_text = "No search data available yet.\nLast Updated: " + datetime.now().strftime(
                    '%Y-%m-%d %H:%M:%S')
            else:
                # Get statistics for different time periods
                all_time = self.get_most_searched()
                today = self.get_most_searched(days=1)
                week = self.get_most_searched(days=7)
                year = self.get_most_searched(days=365)
                user_history = self.get_user_search_history(limit=50)

                stats_text = self._format_stastics(all_time, today, week, year, user_history)  # Changed method name

            # Write to stastics file
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                f.write(stats_text)

            print(f"Stastics file updated successfully at {datetime.now()}")

            # Debug: Read and print file contents
            with open(self.stats_file, 'r', encoding='utf-8') as f:
                content = f.read()
            print(f"Stastics file size: {len(content)} bytes")

        except Exception as e:
            print(f"Error updating stastics file: {e}")
            import traceback
            traceback.print_exc()

    def _format_stastics(self, all_time, today, week, year, user_history):  # Changed method name
        stats_text = "Movie Search Stastics\n"  # Changed heading
        stats_text += "=" * 50 + "\n\n"

        # Add section for each time period
        sections = [
            ("All-Time Most Searched Movies:", all_time),
            ("Today's Most Searched Movies:", today),
            ("This Week's Most Searched Movies:", week),
            ("This Year's Most Searched Movies:", year)
        ]

        for title, data in sections:
            stats_text += f"{title}\n"
            if data:
                stats_text += "\n".join(f"{i + 1}. {movie} ({count} searches)"
                                      for i, (movie, count) in enumerate(data))
            else:
                stats_text += "No searches in this period"
            stats_text += "\n\n"

        # Add user history section
        stats_text += "Recent User Search History:\n"
        stats_text += "=" * 50 + "\n"
        if user_history:
            for search in user_history:
                stats_text += f"\nTime: {search['timestamp']}\n"
                stats_text += f"User: {search['user_name']} (ID: {search['user_id']})\n"
                stats_text += f"Search Type: {search['search_type']}\n"
                stats_text += f"Query: {search['search_query']}\n"
                stats_text += "-" * 30 + "\n"
        else:
            stats_text += "\nNo user search history available yet\n"

        stats_text += f"\nLast Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        return stats_text

# Modify the update_statistics_job to include error handling and logging
async def update_stastics_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        print(f"Starting stastics update job at {datetime.now()}")
        stats = SearchStatistics()
        stats.update_stastics_file()
        print(f"Completed stastics update job at {datetime.now()}")
    except Exception as e:
        print(f"Error in stastics update job: {e}")
        import traceback
        traceback.print_exc()

async def view_searches_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only allow yourself to see the searches
    if update.message.from_user.id == 6822829183:  # Replace with your Telegram ID
        recent_searches = search_logger.get_recent_searches(limit=10)  # Get last 10 searches

        message = "Recent Searches:\n\n"
        for search in recent_searches:
            message += f"👤 User: {search['user_name']}\n"
            message += f"🔍 Query: {search['search_query']}\n"
            message += f"⏰ Time: {search['timestamp']}\n"
            message += f"Type: {search['search_type']}\n\n"

        await update.message.reply_text(message)
    else:
        await update.message.reply_text("You don't have permission to use this command.")


# Add this to your command handlers

class UserActivityManager:
    def __init__(self):
        self.user_activity = {}
        self.load_activity()

    def load_activity(self):
        if Path(LAST_ACTIVITY_FILE).exists():
            try:
                with open(LAST_ACTIVITY_FILE, 'rb') as f:
                    self.user_activity = pickle.load(f)
            except Exception as e:
                print(f"Error loading user activity: {e}")
                self.user_activity = {}

    def save_activity(self):
        try:
            with open(LAST_ACTIVITY_FILE, 'wb') as f:
                pickle.dump(self.user_activity, f)
        except Exception as e:
            print(f"Error saving user activity: {e}")

    def update_user_activity(self, user_id: int, user_name: str):
        self.user_activity[user_id] = {
            'last_active': datetime.now(),
            'name': user_name
        }
        self.save_activity()

    def get_inactive_users(self):
        current_time = datetime.now()
        inactive_users = []

        for user_id, data in self.user_activity.items():
            if (current_time - data['last_active']) >= INACTIVITY_THRESHOLD:
                inactive_users.append({
                    'user_id': user_id,
                    'name': data['name'],
                    'last_active': data['last_active']
                })

        return inactive_users


# Create global instance
activity_manager = UserActivityManager()


# Modify the handle_user_message function to track activity
async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    await delete_message_later(context, update.message.chat_id, update.message.message_id)
    await handle_user_query(update, context)


# Add a new function to check for inactive users
async def check_inactive_users(context: ContextTypes.DEFAULT_TYPE):
    inactive_users = activity_manager.get_inactive_users()

    for user in inactive_users:
        try:
            message = f"Hey {user['name']} 👋,\n\nI am missing you dear! 💫\nIt's been a while since we last chatted. Come back and discover some amazing movies! 🎬"

            await context.bot.send_message(
                chat_id=user['user_id'],
                text=message,
                parse_mode='Markdown'
            )

            # Update the last activity to prevent spam
            activity_manager.update_user_activity(user['user_id'], user['name'])

        except Exception as e:
            print(f"Error sending reminder to user {user['user_id']}: {e}")

class MessageTracker:
    def __init__(self):
        self.messages: Dict[int, Dict[int, datetime]] = {}

    async def add_message(self, chat_id: int, message_id: int):
        if chat_id not in self.messages:
            self.messages[chat_id] = {}
        self.messages[chat_id][message_id] = datetime.now() + timedelta(seconds=DELETE_TIMEOUT)

    async def cleanup_messages(self, context: ContextTypes.DEFAULT_TYPE):
        current_time = datetime.now()
        for chat_id in list(self.messages.keys()):
            for message_id, expiry_time in list(self.messages[chat_id].items()):
                if current_time >= expiry_time:
                    try:
                        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                    except TelegramError:
                        pass  # Message might already be deleted
                    finally:
                        del self.messages[chat_id][message_id]
            if not self.messages[chat_id]:
                del self.messages[chat_id]

message_tracker = MessageTracker()

async def cleanup_job(context: ContextTypes.DEFAULT_TYPE):
    await message_tracker.cleanup_messages(context)

async def delete_message_later(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int):
    await message_tracker.add_message(chat_id, message_id)

async def send_with_warning(message, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None, parse_mode=None):
    try:
        if hasattr(message, 'reply_text'):
            sent_message = await message.reply_text(
                f"{text}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await message.edit_text(
                f"{text}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

        await delete_message_later(context, sent_message.chat_id, sent_message.message_id)
        return sent_message
    except TelegramError as e:
        print(f"Error sending message: {e}")
        return None

async def send_photo_with_warning(message, context: ContextTypes.DEFAULT_TYPE, photo: str, caption: str, reply_markup=None, parse_mode=None):
    try:
        if hasattr(message, 'reply_photo'):
            sent_message = await message.reply_photo(
                photo=photo,
                caption=f"{caption}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await context.bot.send_photo(
                chat_id=message.chat_id,
                photo=photo,
                caption=f"{caption}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

        await delete_message_later(context, sent_message.chat_id, sent_message.message_id)
        return sent_message
    except TelegramError as e:
        print(f"Error sending photo: {e}")
        return None


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    keyboard = [
        [InlineKeyboardButton("  DOWNLOAD MOVIES", callback_data='search_movies')],
        [
            InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
            InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
            InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
        ],
        [InlineKeyboardButton("📈 Popular Movies", callback_data='popular'),
         InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
        [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
        [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_with_warning(
        update.message,
        context,
        f"👋 Hello {user_name}! Welcome to @movieshuba11_bot!\n\nClick on /start to restart or type",
        reply_markup=reply_markup
    )

async def show_start_menu(message, context: ContextTypes.DEFAULT_TYPE):
    # Get user's name from the callback query
    user_name = message._effective_user.first_name if hasattr(message, '_effective_user') else "there"
    keyboard = [
        [InlineKeyboardButton(" Download movies", callback_data='search_movies')],
        [
            InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
            InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
            InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
        ],
        [InlineKeyboardButton("📈 Popular Movies", callback_data='popular')],
        [InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
        [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
        [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_with_warning(
        message,
        context,
        f"👋 Hello {user_name}! Welcome to moviieshubb_bot!\n\nClick on /start to restart or type",
        reply_markup=reply_markup
    )



async def get_random_movies_by_genre(message, context: ContextTypes.DEFAULT_TYPE, genre_id=None):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "sort_by": "popularity.desc",
            "page": 1
        }

        if genre_id:
            params["with_genres"] = genre_id

        response = requests.get(url, params=params)
        response.raise_for_status()
        total_pages = min(response.json().get("total_pages", 1), 500)

        random_page = random.randint(1, total_pages)
        params["page"] = random_page

        response = requests.get(url, params=params)
        response.raise_for_status()

        all_movies = response.json().get("results", [])
        random_movies = random.sample(all_movies, min(5, len(all_movies)))

        response_text = "🎲 Random Movie Suggestions:\n\n"
        keyboard = []
        for i, movie in enumerate(random_movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"
            keyboard.append([InlineKeyboardButton(f"🔍 Search {movie['title']}", callback_data=f'search_specific_{movie["id"]}')])

        keyboard.extend([
            [
                InlineKeyboardButton("👻 Horror", callback_data='random_horror'),
                InlineKeyboardButton("🔪 Crime", callback_data='random_crime'),
                InlineKeyboardButton("💝 Romance", callback_data='random_romance')
            ],
            [InlineKeyboardButton("🎲 More Random", callback_data='random_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching random movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='random_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                                "Sorry, couldn't fetch random movies right now.",
                                reply_markup=reply_markup)


async def get_popular_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/movie/popular"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "🎬 Currently Popular Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching popular movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='popular')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch popular movies right now.",
                              reply_markup=reply_markup)

async def get_horror_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "with_genres": HORROR_GENRE_ID,
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "👻 Popular Horror Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton("👻 More Horror Movies", callback_data='horror_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching horror movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='horror_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch horror movies right now.",
                              reply_markup=reply_markup)

async def get_bollywood_popular_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "region": "IN",
            "with_original_language": "hi",
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "🎬  Bollywood Popular Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching Bollywood movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='bollywood_popular')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch Bollywood movies right now.",
                              reply_markup=reply_markup)


async def search_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    special_case, special_links = special_cases_manager.is_special_case(query)
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Log the search
    search_logger.log_search(user_id, user_name, "movie", query)
    try:
        tmdb_handler = TMDBAPIHandler(TMDB_API_KEY)

        # Search for movie
        results = tmdb_handler.make_request(
            "/search/movie",
            params={"query": query, "language": "en-US"}
        ).get("results", [])

        if results:
            movie = results[0]
            movie_id = movie["id"]

            # Get movie details
            movie_details = tmdb_handler.make_request(f"/movie/{movie_id}")
            providers = tmdb_handler.make_request(f"/movie/{movie_id}/watch/providers").get("results", {}).get("US",
                                                                                                               {}).get(
                "flatrate", [])

        search_url = f"{TMDB_BASE_URL}/search/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        if results:
            movie = results[0]
            movie_id = movie["id"]

            details_url = f"{TMDB_BASE_URL}/movie/{movie_id}"
            watch_providers_url = f"{TMDB_BASE_URL}/movie/{movie_id}/watch/providers"

            details_response = requests.get(details_url, params={"api_key": TMDB_API_KEY})
            providers_response = requests.get(watch_providers_url, params={"api_key": TMDB_API_KEY})

            movie_details = details_response.json()
            providers = providers_response.json().get("results", {}).get("US", {}).get("flatrate", [])

            keyboard = [
                [InlineKeyboardButton(" Search Another Movie", callback_data='search_movies')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            response_text = (
                f"*{movie_details['title']}* ({movie_details.get('release_date', '')[:4]})\n\n"
                f"Plot: {movie_details.get('overview', 'No plot available')}\n\n"
            )

            if providers:
                response_text += "Available on: " + ", ".join(p["provider_name"] for p in providers) + "\n\n"
            else:
                response_text += "Streaming information not available\n\n"

            if special_case and special_links:
                response_text += "Download Links:\n"
                for link in special_links:
                    lang_text = f" ({link['language']})" if link.get('language') else ""
                    response_text += f"• {link['url']}{lang_text}\n"
            else:
                response_text += "download link comming soon msg @balaram129"

            if movie_details.get("poster_path"):
                poster_url = f"{TMDB_IMAGE_BASE_URL}{movie_details['poster_path']}"
                await send_photo_with_warning(update.message, context, photo=poster_url, caption=response_text, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                await send_with_warning(update.message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            keyboard = [
                [InlineKeyboardButton(" Try Again", callback_data='search_movies')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(update.message, context, "No movies found matching your search.", reply_markup=reply_markup)
    except Exception as e:
        print(f"Error in movie search: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(update.message, context,
                              "Sorry, there was an error processing your request. Please try again.",
                              reply_markup=reply_markup)

async def search_by_actor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Log the search
    search_logger.log_search(user_id, user_name, "actor", query)
    try:
        search_url = f"{TMDB_BASE_URL}/search/person"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        if results:
            actor = results[0]
            actor_id = actor["id"]

            actor_details_url = f"{TMDB_BASE_URL}/person/{actor_id}"
            movies_url = f"{TMDB_BASE_URL}/person/{actor_id}/movie_credits"

            actor_details_response = requests.get(actor_details_url, params={"api_key": TMDB_API_KEY})
            movies_response = requests.get(movies_url, params={"api_key": TMDB_API_KEY})

            actor_details = actor_details_response.json()
            movies = movies_response.json().get("cast", [])

            movies_with_rating = [m for m in movies if m.get("vote_average", 0) > 0]
            sorted_movies = sorted(movies_with_rating, key=lambda x: x.get("vote_average", 0), reverse=True)

            popular_movies = [m for m in sorted_movies if m.get("vote_average", 0) >= 7][:4]
            unpopular_movies = [m for m in sorted_movies if m.get("vote_average", 0) < 7][:4]

            response_text = f"🎭 {actor['name']}\n"
            if actor_details.get("birthday"):
                response_text += f"Birthday: {actor_details['birthday']}\n"
            if actor_details.get("place_of_birth"):
                response_text += f"Birthplace: {actor_details['place_of_birth']}\n"

            response_text += "\n📈 Highly Rated Movies:\n"
            for i, movie in enumerate(popular_movies, 1):
                response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
                response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"

            response_text += "\n📉 Other Notable Movies:\n"
            for i, movie in enumerate(unpopular_movies, 1):
                response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
                response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"

            keyboard = [
                [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
                [InlineKeyboardButton(" Search Another Actor", callback_data='search_actor')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            if actor.get("profile_path"):
                actor_image_url = f"{TMDB_IMAGE_BASE_URL}{actor['profile_path']}"
                await send_photo_with_warning(
                    update.message,
                    context,
                    photo=actor_image_url,
                    caption=response_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await send_with_warning(
                    update.message,
                    context,
                    response_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
        else:
            keyboard = [
                [InlineKeyboardButton(" Try Again", callback_data='search_actor')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                update.message,
                context,
                "No actor found matching your search.",
                reply_markup=reply_markup
            )
    except Exception as e:
        print(f"Error in actor search: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='search_actor')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(
            update.message,
            context,
            "Sorry, there was an error processing your request. Please try again.",
            reply_markup=reply_markup
        )
def is_special_case(query):
    query_lower = query.lower().strip()
    for key, case in special_cases_manager.items():
        if query_lower == key.lower() or query_lower in [v.lower() for v in case["variants"]]:
            return True, case["links"]
    return False, []

async def get_genre_movies(message, context: ContextTypes.DEFAULT_TYPE, genre_id: int, genre_name: str):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "with_genres": genre_id,
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = f"🎬 Popular {genre_name} Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching {genre_name} movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data=f'genre_{genre_name.lower()}')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              f"Sorry, couldn't fetch {genre_name} movies right now.",
                              reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_name = query.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    try:
        if query.data.startswith('search_specific_'):
            movie_id = query.data.split('_')[2]
            # Get movie details from TMDB
            url = f"{TMDB_BASE_URL}/movie/{movie_id}"
            response = requests.get(url, params={"api_key": TMDB_API_KEY})
            movie = response.json()

            # Create a message with movie details
            movie_text = f"{movie['title']} ({movie.get('release_date', '')[:4]})"

            # Send a temporary message to user's private chat
            class SimulatedMessage:
                def __init__(self, chat_id, text, from_user):
                    self.chat_id = chat_id
                    self.text = text
                    self.from_user = from_user

                def reply_text(self, *args, **kwargs):
                    return query.message.reply_text(*args, **kwargs)

                def reply_photo(self, *args, **kwargs):
                    return query.message.reply_photo(*args, **kwargs)

            # Create a proper message object
            simulated_message = SimulatedMessage(
                chat_id=query.message.chat_id,
                text=movie['title'],
                from_user=query.from_user
            )

            # Create a proper update object
            class SimulatedUpdate:
                def __init__(self, message):
                    self.message = message

            simulated_update = SimulatedUpdate(simulated_message)

            # Perform the search
            await search_movie(simulated_update, context)
            return
        if query.data == 'genre_horror':
            await get_genre_movies(query.message, context, GENRE_IDS['horror'], "Horror")
        elif query.data == 'genre_romance':
            await get_genre_movies(query.message, context, GENRE_IDS['romance'], "Romance")
        elif query.data == 'genre_crime':
            await get_genre_movies(query.message, context, GENRE_IDS['crime'], "Crime")
        elif query.data == 'random_movies':
            await get_random_movies_by_genre(query.message, context)
        if query.data == 'random_movies':
            await get_random_movies_by_genre(query.message, context)
        elif query.data == 'random_horror':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['horror'])
        elif query.data == 'random_crime':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['crime'])
        elif query.data == 'random_romance':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['romance'])
        elif query.data == 'horror_movies':
            await get_horror_movies(query.message, context)
        elif query.data == 'search_movies':
            USER_CONTEXT[query.message.chat_id] = 'movie'
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "🔍 Just type the name of any movie you want to search for!",
                reply_markup=reply_markup
            )
        elif query.data == 'search_actor':
            USER_CONTEXT[query.message.chat_id] = 'actor'
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "🎭 Just type the name of any actor to see their movies!",
                reply_markup=reply_markup
            )
        elif query.data == 'help':
            help_text = ("📖 How to use this bot:\n\n"
                        "1. Simply type any movie name\n"
                        "2. Or type any actor name to find their movies\n"
                        "3. I'll show you the details\n"
                        "4. Check out popular movies in both Hollywood and Bollywood\n"
                        "5. Try our random movie suggestions by genre!\n"
                        "Need more help? Just type /start to see the main menu again! or msg @balaram129")
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                help_text,
                reply_markup=reply_markup
            )
        elif query.data == 'popular':
            await get_popular_movies(query.message, context)
        elif query.data == 'bollywood_popular':
            await get_bollywood_popular_movies(query.message, context)
        elif query.data == 'start_menu':
            keyboard = [
                [InlineKeyboardButton("🔍 Download movies", callback_data='search_movies'),
                 InlineKeyboardButton("👻 Horror Movies", callback_data='horror_movies')],
                [
                    InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
                    InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
                    InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
                ],
                [InlineKeyboardButton("📈 Popular Movies", callback_data='popular')],
                [InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
                [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
                [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
                [InlineKeyboardButton("❓ Help", callback_data='help')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "👋 Welcome to moviieshubb_bot!\n\nClick on /start to restart or type",
                reply_markup=reply_markup
            )

    except Exception as e:
        print(f"Error in button callback: {e}")
        keyboard = [
            [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(
            query.message,
            context,
            "Sorry, there was an error processing your request. Please try again.",
            reply_markup=reply_markup
        )

async def handle_user_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_context = USER_CONTEXT.get(update.message.chat_id, "movie")
    if user_context == "actor":
        await search_by_actor(update, context)
    else:
        await search_movie(update, context)

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_message_later(context, update.message.chat_id, update.message.message_id)
    await handle_user_query(update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Exception while handling an update: {context.error}")
    if isinstance(context.error, Conflict):
        print("Bot instance already running. Exiting...")
        sys.exit(1)
    elif isinstance(context.error, NetworkError):
        print("Network error occurred. Waiting before retry...")
        await asyncio.sleep(1)
    else:
        print(f"Unexpected error: {context.error}")


def main():
    try:
        application = (
            Application.builder()
            .token(TELEGRAM_TOKEN)
            .build()
        )

        # Add existing handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CallbackQueryHandler(button_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))
        application.add_handler(CommandHandler("viewsearches", view_searches_command))

        # Add error handler
        application.add_error_handler(error_handler)

        # Set up the cleanup job to run every 10 seconds
        job_queue = application.job_queue
        job_queue.run_repeating(cleanup_job, interval=10, first=0)

        # Add the inactive user check job (runs every 6 hours)
        job_queue.run_repeating(check_inactive_users, interval=21600, first=21600)

        # Update stastics more frequently (every 5 minutes)
        job_queue.run_repeating(update_stastics_job, interval=300, first=0)

        # Initial statistics update
        print("Performing initial statistics update...")
        stats = SearchStatistics()
        stats.update_stastics_file()
        print("Initial statistics update completed")

        # Start the bot
        print("Starting bot...")
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

    except Exception as e:
        print(f"Error starting bot: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

# Test the logger
logger = SearchLogger()
logger.log_search(123456, "TestUser", "movie", "Avatar")

# Check recent searches
recent = logger.get_recent_searches()
print("Recent searches:", recent)import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import Conflict, NetworkError, TelegramError
import nest_asyncio
import sys
import random
from typing import Optional, Dict
from datetime import datetime, timedelta
import pickle
from special_cases_managerss import SpecialCasesManager
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import json
from datetime import datetime
from pathlib import Path


class SearchLogger:
    def __init__(self, log_file="search_logs.json"):
        self.log_file = log_file
        self.ensure_log_file_exists()

    def ensure_log_file_exists(self):
        # Create the file with an empty list if it doesn't exist or is empty
        if not Path(self.log_file).exists() or Path(self.log_file).stat().st_size == 0:
            with open(self.log_file, 'w') as f:
                json.dump([], f)

    def log_search(self, user_id: int, user_name: str, search_type: str, search_query: str):
        try:
            # First ensure the file exists and has valid JSON
            self.ensure_log_file_exists()

            # Read existing logs
            try:
                with open(self.log_file, 'r') as f:
                    logs = json.load(f)
            except json.JSONDecodeError:
                # If there's an error reading the JSON, start with an empty list
                logs = []

            # Create new log entry
            log_entry = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "user_id": user_id,
                "user_name": user_name,
                "search_type": search_type,
                "search_query": search_query
            }

            # Add new entry
            logs.append(log_entry)

            # Write back to file
            with open(self.log_file, 'w') as f:
                json.dump(logs, f, indent=2)

        except Exception as e:
            print(f"Error logging search: {e}")

    def get_recent_searches(self, limit: int = 100):
        try:
            # First ensure the file exists and has valid JSON
            self.ensure_log_file_exists()

            with open(self.log_file, 'r') as f:
                try:
                    logs = json.load(f)
                except json.JSONDecodeError:
                    return []
            return logs[-limit:]
        except Exception as e:
            print(f"Error getting recent searches: {e}")
            return []


# Create an instance of the logger
search_logger = SearchLogger()


# After your other global variables
special_cases_manager = SpecialCasesManager()

# Initialize some cases if you want (optional)
special_cases_manager.add_case(
    "pushpa 2",
    ["pushpa2", "pushpa-2", "pushpa2therule", "pushpa 2 the rule"],
    [
        {"url": "https://example4.com", "language": "Hindi"},
        {"url": "https://example5.com", "language": "Telugu"}
    ]
)

special_cases_manager.add_case(
    "venom",
    ["venom", "venom1", "venom2"],
    [
        {"url": "https://www.udlinks.com/3I1l", "language": "hindi"}
    ]
)




nest_asyncio.apply()

TELEGRAM_TOKEN = "7883754025:AAHUDU-_EM4QYome14k_28PQbPTWsl_9w6s"
TMDB_API_KEY = "c3b8704a4df65146c194940351efa9a2"
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
DELETE_TIMEOUT = 420  # 7 minutes in seconds
DISCLAIMER = "⚠️ This message will be deleted in 7 minutes"
HORROR_GENRE_ID = 27  # TMDB's genre ID for horror movies



USER_CONTEXT = {}

GENRE_IDS = {
    'horror': 27,
    'crime': 80,
    'romance': 10749
}


class TMDBAPIHandler:
    def __init__(self, api_key, base_url="https://api.themoviedb.org/3"):
        self.api_key = api_key
        self.base_url = base_url
        self.session = self._create_session()

    def _create_session(self):
        session = requests.Session()

        # Configure retry strategy
        retries = Retry(
            total=5,  # Total number of retries
            backoff_factor=0.5,  # Wait 0.5, 1, 2, 4, 8 seconds between retries
            status_forcelist=[500, 502, 503, 504, 408, 429]  # HTTP status codes to retry on
        )

        # Add retry adapter to session
        adapter = HTTPAdapter(max_retries=retries)
        session.mount('http://', adapter)
        session.mount('https://', adapter)

        return session

    def make_request(self, endpoint, params=None):
        if params is None:
            params = {}

        # Always include API key
        params['api_key'] = self.api_key

        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                response = self.session.get(
                    f"{self.base_url}{endpoint}",
                    params=params,
                    timeout=10  # 10 seconds timeout
                )
                response.raise_for_status()
                return response.json()

            except requests.exceptions.ConnectionError as e:
                if attempt == max_attempts - 1:
                    raise Exception("Unable to connect to TMDB API. Please check your internet connection.") from e
                time.sleep(2 ** attempt)  # Exponential backoff

            except requests.exceptions.Timeout as e:
                if attempt == max_attempts - 1:
                    raise Exception("TMDB API request timed out. Please try again later.") from e
                time.sleep(2 ** attempt)

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:  # Rate limit exceeded
                    retry_after = int(e.response.headers.get('Retry-After', 5))
                    time.sleep(retry_after)
                    continue
                raise Exception(f"TMDB API error: {e.response.status_code}") from e


LAST_ACTIVITY_FILE = "user_activity.pkl"
INACTIVITY_THRESHOLD = timedelta(hours=78)


class SearchStatistics:
    def __init__(self, log_file="search_logs.json", stats_file="stastics.txt"):
        self.log_file = log_file
        self.stats_file = stats_file
        self.search_logger = SearchLogger(log_file)
        # Ensure stastics file exists
        self.update_stastics_file()
        print(f"SearchStatistics initialized. Stats file: {stats_file}")

    def _load_searches(self):
        """Load searches from the log file"""
        try:
            with open(self.log_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def get_most_searched(self, days=None):
        """Get most searched queries within specified days"""
        searches = self._load_searches()
        if not searches:
            return []

        # Filter by date if days is specified
        if days:
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            searches = [s for s in searches if s['timestamp'][:10] >= cutoff_date]

        # Count search queries
        query_counts = {}
        for search in searches:
            query = search['search_query'].lower()
            query_counts[query] = query_counts.get(query, 0) + 1

        # Sort by count and return top 10
        return sorted(query_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    def get_user_search_history(self, limit=50):
        """Get recent user search history"""
        searches = self._load_searches()
        return searches[-limit:] if searches else []

    def update_stastics_file(self):  # Changed method name to match file name
        try:
            print(f"Updating stastics file at {datetime.now()}")

            # Check if log file exists and has data
            if not Path(self.log_file).exists():
                print(f"Log file {self.log_file} does not exist!")
                return

            # Load searches
            searches = self._load_searches()
            if not searches:
                print("No search data found in logs")
                stats_text = "No search data available yet.\nLast Updated: " + datetime.now().strftime(
                    '%Y-%m-%d %H:%M:%S')
            else:
                # Get statistics for different time periods
                all_time = self.get_most_searched()
                today = self.get_most_searched(days=1)
                week = self.get_most_searched(days=7)
                year = self.get_most_searched(days=365)
                user_history = self.get_user_search_history(limit=50)

                stats_text = self._format_stastics(all_time, today, week, year, user_history)  # Changed method name

            # Write to stastics file
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                f.write(stats_text)

            print(f"Stastics file updated successfully at {datetime.now()}")

            # Debug: Read and print file contents
            with open(self.stats_file, 'r', encoding='utf-8') as f:
                content = f.read()
            print(f"Stastics file size: {len(content)} bytes")

        except Exception as e:
            print(f"Error updating stastics file: {e}")
            import traceback
            traceback.print_exc()

    def _format_stastics(self, all_time, today, week, year, user_history):  # Changed method name
        stats_text = "Movie Search Stastics\n"  # Changed heading
        stats_text += "=" * 50 + "\n\n"

        # Add section for each time period
        sections = [
            ("All-Time Most Searched Movies:", all_time),
            ("Today's Most Searched Movies:", today),
            ("This Week's Most Searched Movies:", week),
            ("This Year's Most Searched Movies:", year)
        ]

        for title, data in sections:
            stats_text += f"{title}\n"
            if data:
                stats_text += "\n".join(f"{i + 1}. {movie} ({count} searches)"
                                      for i, (movie, count) in enumerate(data))
            else:
                stats_text += "No searches in this period"
            stats_text += "\n\n"

        # Add user history section
        stats_text += "Recent User Search History:\n"
        stats_text += "=" * 50 + "\n"
        if user_history:
            for search in user_history:
                stats_text += f"\nTime: {search['timestamp']}\n"
                stats_text += f"User: {search['user_name']} (ID: {search['user_id']})\n"
                stats_text += f"Search Type: {search['search_type']}\n"
                stats_text += f"Query: {search['search_query']}\n"
                stats_text += "-" * 30 + "\n"
        else:
            stats_text += "\nNo user search history available yet\n"

        stats_text += f"\nLast Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        return stats_text

# Modify the update_statistics_job to include error handling and logging
async def update_stastics_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        print(f"Starting stastics update job at {datetime.now()}")
        stats = SearchStatistics()
        stats.update_stastics_file()
        print(f"Completed stastics update job at {datetime.now()}")
    except Exception as e:
        print(f"Error in stastics update job: {e}")
        import traceback
        traceback.print_exc()

async def view_searches_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only allow yourself to see the searches
    if update.message.from_user.id == 6822829183:  # Replace with your Telegram ID
        recent_searches = search_logger.get_recent_searches(limit=10)  # Get last 10 searches

        message = "Recent Searches:\n\n"
        for search in recent_searches:
            message += f"👤 User: {search['user_name']}\n"
            message += f"🔍 Query: {search['search_query']}\n"
            message += f"⏰ Time: {search['timestamp']}\n"
            message += f"Type: {search['search_type']}\n\n"

        await update.message.reply_text(message)
    else:
        await update.message.reply_text("You don't have permission to use this command.")


# Add this to your command handlers

class UserActivityManager:
    def __init__(self):
        self.user_activity = {}
        self.load_activity()

    def load_activity(self):
        if Path(LAST_ACTIVITY_FILE).exists():
            try:
                with open(LAST_ACTIVITY_FILE, 'rb') as f:
                    self.user_activity = pickle.load(f)
            except Exception as e:
                print(f"Error loading user activity: {e}")
                self.user_activity = {}

    def save_activity(self):
        try:
            with open(LAST_ACTIVITY_FILE, 'wb') as f:
                pickle.dump(self.user_activity, f)
        except Exception as e:
            print(f"Error saving user activity: {e}")

    def update_user_activity(self, user_id: int, user_name: str):
        self.user_activity[user_id] = {
            'last_active': datetime.now(),
            'name': user_name
        }
        self.save_activity()

    def get_inactive_users(self):
        current_time = datetime.now()
        inactive_users = []

        for user_id, data in self.user_activity.items():
            if (current_time - data['last_active']) >= INACTIVITY_THRESHOLD:
                inactive_users.append({
                    'user_id': user_id,
                    'name': data['name'],
                    'last_active': data['last_active']
                })

        return inactive_users


# Create global instance
activity_manager = UserActivityManager()


# Modify the handle_user_message function to track activity
async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    await delete_message_later(context, update.message.chat_id, update.message.message_id)
    await handle_user_query(update, context)


# Add a new function to check for inactive users
async def check_inactive_users(context: ContextTypes.DEFAULT_TYPE):
    inactive_users = activity_manager.get_inactive_users()

    for user in inactive_users:
        try:
            message = f"Hey {user['name']} 👋,\n\nI am missing you dear! 💫\nIt's been a while since we last chatted. Come back and discover some amazing movies! 🎬"

            await context.bot.send_message(
                chat_id=user['user_id'],
                text=message,
                parse_mode='Markdown'
            )

            # Update the last activity to prevent spam
            activity_manager.update_user_activity(user['user_id'], user['name'])

        except Exception as e:
            print(f"Error sending reminder to user {user['user_id']}: {e}")

class MessageTracker:
    def __init__(self):
        self.messages: Dict[int, Dict[int, datetime]] = {}

    async def add_message(self, chat_id: int, message_id: int):
        if chat_id not in self.messages:
            self.messages[chat_id] = {}
        self.messages[chat_id][message_id] = datetime.now() + timedelta(seconds=DELETE_TIMEOUT)

    async def cleanup_messages(self, context: ContextTypes.DEFAULT_TYPE):
        current_time = datetime.now()
        for chat_id in list(self.messages.keys()):
            for message_id, expiry_time in list(self.messages[chat_id].items()):
                if current_time >= expiry_time:
                    try:
                        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                    except TelegramError:
                        pass  # Message might already be deleted
                    finally:
                        del self.messages[chat_id][message_id]
            if not self.messages[chat_id]:
                del self.messages[chat_id]

message_tracker = MessageTracker()

async def cleanup_job(context: ContextTypes.DEFAULT_TYPE):
    await message_tracker.cleanup_messages(context)

async def delete_message_later(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int):
    await message_tracker.add_message(chat_id, message_id)

async def send_with_warning(message, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None, parse_mode=None):
    try:
        if hasattr(message, 'reply_text'):
            sent_message = await message.reply_text(
                f"{text}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await message.edit_text(
                f"{text}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

        await delete_message_later(context, sent_message.chat_id, sent_message.message_id)
        return sent_message
    except TelegramError as e:
        print(f"Error sending message: {e}")
        return None

async def send_photo_with_warning(message, context: ContextTypes.DEFAULT_TYPE, photo: str, caption: str, reply_markup=None, parse_mode=None):
    try:
        if hasattr(message, 'reply_photo'):
            sent_message = await message.reply_photo(
                photo=photo,
                caption=f"{caption}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await context.bot.send_photo(
                chat_id=message.chat_id,
                photo=photo,
                caption=f"{caption}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

        await delete_message_later(context, sent_message.chat_id, sent_message.message_id)
        return sent_message
    except TelegramError as e:
        print(f"Error sending photo: {e}")
        return None


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    keyboard = [
        [InlineKeyboardButton("  DOWNLOAD MOVIES", callback_data='search_movies')],
        [
            InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
            InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
            InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
        ],
        [InlineKeyboardButton("📈 Popular Movies", callback_data='popular'),
         InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
        [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
        [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_with_warning(
        update.message,
        context,
        f"👋 Hello {user_name}! Welcome to @movieshuba11_bot!\n\nClick on /start to restart or type",
        reply_markup=reply_markup
    )

async def show_start_menu(message, context: ContextTypes.DEFAULT_TYPE):
    # Get user's name from the callback query
    user_name = message._effective_user.first_name if hasattr(message, '_effective_user') else "there"
    keyboard = [
        [InlineKeyboardButton(" Download movies", callback_data='search_movies')],
        [
            InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
            InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
            InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
        ],
        [InlineKeyboardButton("📈 Popular Movies", callback_data='popular')],
        [InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
        [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
        [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_with_warning(
        message,
        context,
        f"👋 Hello {user_name}! Welcome to moviieshubb_bot!\n\nClick on /start to restart or type",
        reply_markup=reply_markup
    )



async def get_random_movies_by_genre(message, context: ContextTypes.DEFAULT_TYPE, genre_id=None):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "sort_by": "popularity.desc",
            "page": 1
        }

        if genre_id:
            params["with_genres"] = genre_id

        response = requests.get(url, params=params)
        response.raise_for_status()
        total_pages = min(response.json().get("total_pages", 1), 500)

        random_page = random.randint(1, total_pages)
        params["page"] = random_page

        response = requests.get(url, params=params)
        response.raise_for_status()

        all_movies = response.json().get("results", [])
        random_movies = random.sample(all_movies, min(5, len(all_movies)))

        response_text = "🎲 Random Movie Suggestions:\n\n"
        keyboard = []
        for i, movie in enumerate(random_movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"
            keyboard.append([InlineKeyboardButton(f"🔍 Search {movie['title']}", callback_data=f'search_specific_{movie["id"]}')])

        keyboard.extend([
            [
                InlineKeyboardButton("👻 Horror", callback_data='random_horror'),
                InlineKeyboardButton("🔪 Crime", callback_data='random_crime'),
                InlineKeyboardButton("💝 Romance", callback_data='random_romance')
            ],
            [InlineKeyboardButton("🎲 More Random", callback_data='random_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching random movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='random_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                                "Sorry, couldn't fetch random movies right now.",
                                reply_markup=reply_markup)


async def get_popular_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/movie/popular"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "🎬 Currently Popular Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching popular movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='popular')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch popular movies right now.",
                              reply_markup=reply_markup)

async def get_horror_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "with_genres": HORROR_GENRE_ID,
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "👻 Popular Horror Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton("👻 More Horror Movies", callback_data='horror_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching horror movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='horror_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch horror movies right now.",
                              reply_markup=reply_markup)

async def get_bollywood_popular_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "region": "IN",
            "with_original_language": "hi",
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "🎬  Bollywood Popular Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching Bollywood movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='bollywood_popular')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch Bollywood movies right now.",
                              reply_markup=reply_markup)


async def search_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    special_case, special_links = special_cases_manager.is_special_case(query)
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Log the search
    search_logger.log_search(user_id, user_name, "movie", query)
    try:
        tmdb_handler = TMDBAPIHandler(TMDB_API_KEY)

        # Search for movie
        results = tmdb_handler.make_request(
            "/search/movie",
            params={"query": query, "language": "en-US"}
        ).get("results", [])

        if results:
            movie = results[0]
            movie_id = movie["id"]

            # Get movie details
            movie_details = tmdb_handler.make_request(f"/movie/{movie_id}")
            providers = tmdb_handler.make_request(f"/movie/{movie_id}/watch/providers").get("results", {}).get("US",
                                                                                                               {}).get(
                "flatrate", [])

        search_url = f"{TMDB_BASE_URL}/search/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        if results:
            movie = results[0]
            movie_id = movie["id"]

            details_url = f"{TMDB_BASE_URL}/movie/{movie_id}"
            watch_providers_url = f"{TMDB_BASE_URL}/movie/{movie_id}/watch/providers"

            details_response = requests.get(details_url, params={"api_key": TMDB_API_KEY})
            providers_response = requests.get(watch_providers_url, params={"api_key": TMDB_API_KEY})

            movie_details = details_response.json()
            providers = providers_response.json().get("results", {}).get("US", {}).get("flatrate", [])

            keyboard = [
                [InlineKeyboardButton(" Search Another Movie", callback_data='search_movies')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            response_text = (
                f"*{movie_details['title']}* ({movie_details.get('release_date', '')[:4]})\n\n"
                f"Plot: {movie_details.get('overview', 'No plot available')}\n\n"
            )

            if providers:
                response_text += "Available on: " + ", ".join(p["provider_name"] for p in providers) + "\n\n"
            else:
                response_text += "Streaming information not available\n\n"

            if special_case and special_links:
                response_text += "Download Links:\n"
                for link in special_links:
                    lang_text = f" ({link['language']})" if link.get('language') else ""
                    response_text += f"• {link['url']}{lang_text}\n"
            else:
                response_text += "download link comming soon msg @balaram129"

            if movie_details.get("poster_path"):
                poster_url = f"{TMDB_IMAGE_BASE_URL}{movie_details['poster_path']}"
                await send_photo_with_warning(update.message, context, photo=poster_url, caption=response_text, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                await send_with_warning(update.message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            keyboard = [
                [InlineKeyboardButton(" Try Again", callback_data='search_movies')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(update.message, context, "No movies found matching your search.", reply_markup=reply_markup)
    except Exception as e:
        print(f"Error in movie search: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(update.message, context,
                              "Sorry, there was an error processing your request. Please try again.",
                              reply_markup=reply_markup)

async def search_by_actor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Log the search
    search_logger.log_search(user_id, user_name, "actor", query)
    try:
        search_url = f"{TMDB_BASE_URL}/search/person"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        if results:
            actor = results[0]
            actor_id = actor["id"]

            actor_details_url = f"{TMDB_BASE_URL}/person/{actor_id}"
            movies_url = f"{TMDB_BASE_URL}/person/{actor_id}/movie_credits"

            actor_details_response = requests.get(actor_details_url, params={"api_key": TMDB_API_KEY})
            movies_response = requests.get(movies_url, params={"api_key": TMDB_API_KEY})

            actor_details = actor_details_response.json()
            movies = movies_response.json().get("cast", [])

            movies_with_rating = [m for m in movies if m.get("vote_average", 0) > 0]
            sorted_movies = sorted(movies_with_rating, key=lambda x: x.get("vote_average", 0), reverse=True)

            popular_movies = [m for m in sorted_movies if m.get("vote_average", 0) >= 7][:4]
            unpopular_movies = [m for m in sorted_movies if m.get("vote_average", 0) < 7][:4]

            response_text = f"🎭 {actor['name']}\n"
            if actor_details.get("birthday"):
                response_text += f"Birthday: {actor_details['birthday']}\n"
            if actor_details.get("place_of_birth"):
                response_text += f"Birthplace: {actor_details['place_of_birth']}\n"

            response_text += "\n📈 Highly Rated Movies:\n"
            for i, movie in enumerate(popular_movies, 1):
                response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
                response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"

            response_text += "\n📉 Other Notable Movies:\n"
            for i, movie in enumerate(unpopular_movies, 1):
                response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
                response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"

            keyboard = [
                [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
                [InlineKeyboardButton(" Search Another Actor", callback_data='search_actor')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            if actor.get("profile_path"):
                actor_image_url = f"{TMDB_IMAGE_BASE_URL}{actor['profile_path']}"
                await send_photo_with_warning(
                    update.message,
                    context,
                    photo=actor_image_url,
                    caption=response_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await send_with_warning(
                    update.message,
                    context,
                    response_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
        else:
            keyboard = [
                [InlineKeyboardButton(" Try Again", callback_data='search_actor')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                update.message,
                context,
                "No actor found matching your search.",
                reply_markup=reply_markup
            )
    except Exception as e:
        print(f"Error in actor search: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='search_actor')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(
            update.message,
            context,
            "Sorry, there was an error processing your request. Please try again.",
            reply_markup=reply_markup
        )
def is_special_case(query):
    query_lower = query.lower().strip()
    for key, case in special_cases_manager.items():
        if query_lower == key.lower() or query_lower in [v.lower() for v in case["variants"]]:
            return True, case["links"]
    return False, []

async def get_genre_movies(message, context: ContextTypes.DEFAULT_TYPE, genre_id: int, genre_name: str):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "with_genres": genre_id,
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = f"🎬 Popular {genre_name} Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching {genre_name} movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data=f'genre_{genre_name.lower()}')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              f"Sorry, couldn't fetch {genre_name} movies right now.",
                              reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_name = query.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    try:
        if query.data.startswith('search_specific_'):
            movie_id = query.data.split('_')[2]
            # Get movie details from TMDB
            url = f"{TMDB_BASE_URL}/movie/{movie_id}"
            response = requests.get(url, params={"api_key": TMDB_API_KEY})
            movie = response.json()

            # Create a message with movie details
            movie_text = f"{movie['title']} ({movie.get('release_date', '')[:4]})"

            # Send a temporary message to user's private chat
            class SimulatedMessage:
                def __init__(self, chat_id, text, from_user):
                    self.chat_id = chat_id
                    self.text = text
                    self.from_user = from_user

                def reply_text(self, *args, **kwargs):
                    return query.message.reply_text(*args, **kwargs)

                def reply_photo(self, *args, **kwargs):
                    return query.message.reply_photo(*args, **kwargs)

            # Create a proper message object
            simulated_message = SimulatedMessage(
                chat_id=query.message.chat_id,
                text=movie['title'],
                from_user=query.from_user
            )

            # Create a proper update object
            class SimulatedUpdate:
                def __init__(self, message):
                    self.message = message

            simulated_update = SimulatedUpdate(simulated_message)

            # Perform the search
            await search_movie(simulated_update, context)
            return
        if query.data == 'genre_horror':
            await get_genre_movies(query.message, context, GENRE_IDS['horror'], "Horror")
        elif query.data == 'genre_romance':
            await get_genre_movies(query.message, context, GENRE_IDS['romance'], "Romance")
        elif query.data == 'genre_crime':
            await get_genre_movies(query.message, context, GENRE_IDS['crime'], "Crime")
        elif query.data == 'random_movies':
            await get_random_movies_by_genre(query.message, context)
        if query.data == 'random_movies':
            await get_random_movies_by_genre(query.message, context)
        elif query.data == 'random_horror':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['horror'])
        elif query.data == 'random_crime':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['crime'])
        elif query.data == 'random_romance':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['romance'])
        elif query.data == 'horror_movies':
            await get_horror_movies(query.message, context)
        elif query.data == 'search_movies':
            USER_CONTEXT[query.message.chat_id] = 'movie'
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "🔍 Just type the name of any movie you want to search for!",
                reply_markup=reply_markup
            )
        elif query.data == 'search_actor':
            USER_CONTEXT[query.message.chat_id] = 'actor'
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "🎭 Just type the name of any actor to see their movies!",
                reply_markup=reply_markup
            )
        elif query.data == 'help':
            help_text = ("📖 How to use this bot:\n\n"
                        "1. Simply type any movie name\n"
                        "2. Or type any actor name to find their movies\n"
                        "3. I'll show you the details\n"
                        "4. Check out popular movies in both Hollywood and Bollywood\n"
                        "5. Try our random movie suggestions by genre!\n"
                        "Need more help? Just type /start to see the main menu again! or msg @balaram129")
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                help_text,
                reply_markup=reply_markup
            )
        elif query.data == 'popular':
            await get_popular_movies(query.message, context)
        elif query.data == 'bollywood_popular':
            await get_bollywood_popular_movies(query.message, context)
        elif query.data == 'start_menu':
            keyboard = [
                [InlineKeyboardButton("🔍 Download movies", callback_data='search_movies'),
                 InlineKeyboardButton("👻 Horror Movies", callback_data='horror_movies')],
                [
                    InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
                    InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
                    InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
                ],
                [InlineKeyboardButton("📈 Popular Movies", callback_data='popular')],
                [InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
                [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
                [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
                [InlineKeyboardButton("❓ Help", callback_data='help')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "👋 Welcome to moviieshubb_bot!\n\nClick on /start to restart or type",
                reply_markup=reply_markup
            )

    except Exception as e:
        print(f"Error in button callback: {e}")
        keyboard = [
            [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(
            query.message,
            context,
            "Sorry, there was an error processing your request. Please try again.",
            reply_markup=reply_markup
        )

async def handle_user_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_context = USER_CONTEXT.get(update.message.chat_id, "movie")
    if user_context == "actor":
        await search_by_actor(update, context)
    else:
        await search_movie(update, context)

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_message_later(context, update.message.chat_id, update.message.message_id)
    await handle_user_query(update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Exception while handling an update: {context.error}")
    if isinstance(context.error, Conflict):
        print("Bot instance already running. Exiting...")
        sys.exit(1)
    elif isinstance(context.error, NetworkError):
        print("Network error occurred. Waiting before retry...")
        await asyncio.sleep(1)
    else:
        print(f"Unexpected error: {context.error}")


def main():
    try:
        application = (
            Application.builder()
            .token(TELEGRAM_TOKEN)
            .build()
        )

        # Add existing handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CallbackQueryHandler(button_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))
        application.add_handler(CommandHandler("viewsearches", view_searches_command))

        # Add error handler
        application.add_error_handler(error_handler)

        # Set up the cleanup job to run every 10 seconds
        job_queue = application.job_queue
        job_queue.run_repeating(cleanup_job, interval=10, first=0)

        # Add the inactive user check job (runs every 6 hours)
        job_queue.run_repeating(check_inactive_users, interval=21600, first=21600)

        # Update stastics more frequently (every 5 minutes)
        job_queue.run_repeating(update_stastics_job, interval=300, first=0)

        # Initial statistics update
        print("Performing initial statistics update...")
        stats = SearchStatistics()
        stats.update_stastics_file()
        print("Initial statistics update completed")

        # Start the bot
        print("Starting bot...")
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

    except Exception as e:
        print(f"Error starting bot: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

# Test the logger
logger = SearchLogger()
logger.log_search(123456, "TestUser", "movie", "Avatar")

# Check recent searches
recent = logger.get_recent_searches()
print("Recent searches:", recent)import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import Conflict, NetworkError, TelegramError
import nest_asyncio
import sys
import random
from typing import Optional, Dict
from datetime import datetime, timedelta
import pickle
from special_cases_managerss import SpecialCasesManager
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import json
from datetime import datetime
from pathlib import Path


class SearchLogger:
    def __init__(self, log_file="search_logs.json"):
        self.log_file = log_file
        self.ensure_log_file_exists()

    def ensure_log_file_exists(self):
        # Create the file with an empty list if it doesn't exist or is empty
        if not Path(self.log_file).exists() or Path(self.log_file).stat().st_size == 0:
            with open(self.log_file, 'w') as f:
                json.dump([], f)

    def log_search(self, user_id: int, user_name: str, search_type: str, search_query: str):
        try:
            # First ensure the file exists and has valid JSON
            self.ensure_log_file_exists()

            # Read existing logs
            try:
                with open(self.log_file, 'r') as f:
                    logs = json.load(f)
            except json.JSONDecodeError:
                # If there's an error reading the JSON, start with an empty list
                logs = []

            # Create new log entry
            log_entry = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "user_id": user_id,
                "user_name": user_name,
                "search_type": search_type,
                "search_query": search_query
            }

            # Add new entry
            logs.append(log_entry)

            # Write back to file
            with open(self.log_file, 'w') as f:
                json.dump(logs, f, indent=2)

        except Exception as e:
            print(f"Error logging search: {e}")

    def get_recent_searches(self, limit: int = 100):
        try:
            # First ensure the file exists and has valid JSON
            self.ensure_log_file_exists()

            with open(self.log_file, 'r') as f:
                try:
                    logs = json.load(f)
                except json.JSONDecodeError:
                    return []
            return logs[-limit:]
        except Exception as e:
            print(f"Error getting recent searches: {e}")
            return []


# Create an instance of the logger
search_logger = SearchLogger()


# After your other global variables
special_cases_manager = SpecialCasesManager()

# Initialize some cases if you want (optional)
special_cases_manager.add_case(
    "pushpa 2",
    ["pushpa2", "pushpa-2", "pushpa2therule", "pushpa 2 the rule"],
    [
        {"url": "https://example4.com", "language": "Hindi"},
        {"url": "https://example5.com", "language": "Telugu"}
    ]
)

special_cases_manager.add_case(
    "venom",
    ["venom", "venom1", "venom2"],
    [
        {"url": "https://www.udlinks.com/3I1l", "language": "hindi"}
    ]
)




nest_asyncio.apply()

TELEGRAM_TOKEN = "7883754025:AAHUDU-_EM4QYome14k_28PQbPTWsl_9w6s"
TMDB_API_KEY = "c3b8704a4df65146c194940351efa9a2"
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
DELETE_TIMEOUT = 420  # 7 minutes in seconds
DISCLAIMER = "⚠️ This message will be deleted in 7 minutes"
HORROR_GENRE_ID = 27  # TMDB's genre ID for horror movies



USER_CONTEXT = {}

GENRE_IDS = {
    'horror': 27,
    'crime': 80,
    'romance': 10749
}


class TMDBAPIHandler:
    def __init__(self, api_key, base_url="https://api.themoviedb.org/3"):
        self.api_key = api_key
        self.base_url = base_url
        self.session = self._create_session()

    def _create_session(self):
        session = requests.Session()

        # Configure retry strategy
        retries = Retry(
            total=5,  # Total number of retries
            backoff_factor=0.5,  # Wait 0.5, 1, 2, 4, 8 seconds between retries
            status_forcelist=[500, 502, 503, 504, 408, 429]  # HTTP status codes to retry on
        )

        # Add retry adapter to session
        adapter = HTTPAdapter(max_retries=retries)
        session.mount('http://', adapter)
        session.mount('https://', adapter)

        return session

    def make_request(self, endpoint, params=None):
        if params is None:
            params = {}

        # Always include API key
        params['api_key'] = self.api_key

        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                response = self.session.get(
                    f"{self.base_url}{endpoint}",
                    params=params,
                    timeout=10  # 10 seconds timeout
                )
                response.raise_for_status()
                return response.json()

            except requests.exceptions.ConnectionError as e:
                if attempt == max_attempts - 1:
                    raise Exception("Unable to connect to TMDB API. Please check your internet connection.") from e
                time.sleep(2 ** attempt)  # Exponential backoff

            except requests.exceptions.Timeout as e:
                if attempt == max_attempts - 1:
                    raise Exception("TMDB API request timed out. Please try again later.") from e
                time.sleep(2 ** attempt)

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:  # Rate limit exceeded
                    retry_after = int(e.response.headers.get('Retry-After', 5))
                    time.sleep(retry_after)
                    continue
                raise Exception(f"TMDB API error: {e.response.status_code}") from e


LAST_ACTIVITY_FILE = "user_activity.pkl"
INACTIVITY_THRESHOLD = timedelta(hours=78)


class SearchStatistics:
    def __init__(self, log_file="search_logs.json", stats_file="stastics.txt"):
        self.log_file = log_file
        self.stats_file = stats_file
        self.search_logger = SearchLogger(log_file)
        # Ensure stastics file exists
        self.update_stastics_file()
        print(f"SearchStatistics initialized. Stats file: {stats_file}")

    def _load_searches(self):
        """Load searches from the log file"""
        try:
            with open(self.log_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def get_most_searched(self, days=None):
        """Get most searched queries within specified days"""
        searches = self._load_searches()
        if not searches:
            return []

        # Filter by date if days is specified
        if days:
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            searches = [s for s in searches if s['timestamp'][:10] >= cutoff_date]

        # Count search queries
        query_counts = {}
        for search in searches:
            query = search['search_query'].lower()
            query_counts[query] = query_counts.get(query, 0) + 1

        # Sort by count and return top 10
        return sorted(query_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    def get_user_search_history(self, limit=50):
        """Get recent user search history"""
        searches = self._load_searches()
        return searches[-limit:] if searches else []

    def update_stastics_file(self):  # Changed method name to match file name
        try:
            print(f"Updating stastics file at {datetime.now()}")

            # Check if log file exists and has data
            if not Path(self.log_file).exists():
                print(f"Log file {self.log_file} does not exist!")
                return

            # Load searches
            searches = self._load_searches()
            if not searches:
                print("No search data found in logs")
                stats_text = "No search data available yet.\nLast Updated: " + datetime.now().strftime(
                    '%Y-%m-%d %H:%M:%S')
            else:
                # Get statistics for different time periods
                all_time = self.get_most_searched()
                today = self.get_most_searched(days=1)
                week = self.get_most_searched(days=7)
                year = self.get_most_searched(days=365)
                user_history = self.get_user_search_history(limit=50)

                stats_text = self._format_stastics(all_time, today, week, year, user_history)  # Changed method name

            # Write to stastics file
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                f.write(stats_text)

            print(f"Stastics file updated successfully at {datetime.now()}")

            # Debug: Read and print file contents
            with open(self.stats_file, 'r', encoding='utf-8') as f:
                content = f.read()
            print(f"Stastics file size: {len(content)} bytes")

        except Exception as e:
            print(f"Error updating stastics file: {e}")
            import traceback
            traceback.print_exc()

    def _format_stastics(self, all_time, today, week, year, user_history):  # Changed method name
        stats_text = "Movie Search Stastics\n"  # Changed heading
        stats_text += "=" * 50 + "\n\n"

        # Add section for each time period
        sections = [
            ("All-Time Most Searched Movies:", all_time),
            ("Today's Most Searched Movies:", today),
            ("This Week's Most Searched Movies:", week),
            ("This Year's Most Searched Movies:", year)
        ]

        for title, data in sections:
            stats_text += f"{title}\n"
            if data:
                stats_text += "\n".join(f"{i + 1}. {movie} ({count} searches)"
                                      for i, (movie, count) in enumerate(data))
            else:
                stats_text += "No searches in this period"
            stats_text += "\n\n"

        # Add user history section
        stats_text += "Recent User Search History:\n"
        stats_text += "=" * 50 + "\n"
        if user_history:
            for search in user_history:
                stats_text += f"\nTime: {search['timestamp']}\n"
                stats_text += f"User: {search['user_name']} (ID: {search['user_id']})\n"
                stats_text += f"Search Type: {search['search_type']}\n"
                stats_text += f"Query: {search['search_query']}\n"
                stats_text += "-" * 30 + "\n"
        else:
            stats_text += "\nNo user search history available yet\n"

        stats_text += f"\nLast Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        return stats_text

# Modify the update_statistics_job to include error handling and logging
async def update_stastics_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        print(f"Starting stastics update job at {datetime.now()}")
        stats = SearchStatistics()
        stats.update_stastics_file()
        print(f"Completed stastics update job at {datetime.now()}")
    except Exception as e:
        print(f"Error in stastics update job: {e}")
        import traceback
        traceback.print_exc()

async def view_searches_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only allow yourself to see the searches
    if update.message.from_user.id == 6822829183:  # Replace with your Telegram ID
        recent_searches = search_logger.get_recent_searches(limit=10)  # Get last 10 searches

        message = "Recent Searches:\n\n"
        for search in recent_searches:
            message += f"👤 User: {search['user_name']}\n"
            message += f"🔍 Query: {search['search_query']}\n"
            message += f"⏰ Time: {search['timestamp']}\n"
            message += f"Type: {search['search_type']}\n\n"

        await update.message.reply_text(message)
    else:
        await update.message.reply_text("You don't have permission to use this command.")


# Add this to your command handlers

class UserActivityManager:
    def __init__(self):
        self.user_activity = {}
        self.load_activity()

    def load_activity(self):
        if Path(LAST_ACTIVITY_FILE).exists():
            try:
                with open(LAST_ACTIVITY_FILE, 'rb') as f:
                    self.user_activity = pickle.load(f)
            except Exception as e:
                print(f"Error loading user activity: {e}")
                self.user_activity = {}

    def save_activity(self):
        try:
            with open(LAST_ACTIVITY_FILE, 'wb') as f:
                pickle.dump(self.user_activity, f)
        except Exception as e:
            print(f"Error saving user activity: {e}")

    def update_user_activity(self, user_id: int, user_name: str):
        self.user_activity[user_id] = {
            'last_active': datetime.now(),
            'name': user_name
        }
        self.save_activity()

    def get_inactive_users(self):
        current_time = datetime.now()
        inactive_users = []

        for user_id, data in self.user_activity.items():
            if (current_time - data['last_active']) >= INACTIVITY_THRESHOLD:
                inactive_users.append({
                    'user_id': user_id,
                    'name': data['name'],
                    'last_active': data['last_active']
                })

        return inactive_users


# Create global instance
activity_manager = UserActivityManager()


# Modify the handle_user_message function to track activity
async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    await delete_message_later(context, update.message.chat_id, update.message.message_id)
    await handle_user_query(update, context)


# Add a new function to check for inactive users
async def check_inactive_users(context: ContextTypes.DEFAULT_TYPE):
    inactive_users = activity_manager.get_inactive_users()

    for user in inactive_users:
        try:
            message = f"Hey {user['name']} 👋,\n\nI am missing you dear! 💫\nIt's been a while since we last chatted. Come back and discover some amazing movies! 🎬"

            await context.bot.send_message(
                chat_id=user['user_id'],
                text=message,
                parse_mode='Markdown'
            )

            # Update the last activity to prevent spam
            activity_manager.update_user_activity(user['user_id'], user['name'])

        except Exception as e:
            print(f"Error sending reminder to user {user['user_id']}: {e}")

class MessageTracker:
    def __init__(self):
        self.messages: Dict[int, Dict[int, datetime]] = {}

    async def add_message(self, chat_id: int, message_id: int):
        if chat_id not in self.messages:
            self.messages[chat_id] = {}
        self.messages[chat_id][message_id] = datetime.now() + timedelta(seconds=DELETE_TIMEOUT)

    async def cleanup_messages(self, context: ContextTypes.DEFAULT_TYPE):
        current_time = datetime.now()
        for chat_id in list(self.messages.keys()):
            for message_id, expiry_time in list(self.messages[chat_id].items()):
                if current_time >= expiry_time:
                    try:
                        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                    except TelegramError:
                        pass  # Message might already be deleted
                    finally:
                        del self.messages[chat_id][message_id]
            if not self.messages[chat_id]:
                del self.messages[chat_id]

message_tracker = MessageTracker()

async def cleanup_job(context: ContextTypes.DEFAULT_TYPE):
    await message_tracker.cleanup_messages(context)

async def delete_message_later(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int):
    await message_tracker.add_message(chat_id, message_id)

async def send_with_warning(message, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None, parse_mode=None):
    try:
        if hasattr(message, 'reply_text'):
            sent_message = await message.reply_text(
                f"{text}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await message.edit_text(
                f"{text}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

        await delete_message_later(context, sent_message.chat_id, sent_message.message_id)
        return sent_message
    except TelegramError as e:
        print(f"Error sending message: {e}")
        return None

async def send_photo_with_warning(message, context: ContextTypes.DEFAULT_TYPE, photo: str, caption: str, reply_markup=None, parse_mode=None):
    try:
        if hasattr(message, 'reply_photo'):
            sent_message = await message.reply_photo(
                photo=photo,
                caption=f"{caption}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await context.bot.send_photo(
                chat_id=message.chat_id,
                photo=photo,
                caption=f"{caption}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

        await delete_message_later(context, sent_message.chat_id, sent_message.message_id)
        return sent_message
    except TelegramError as e:
        print(f"Error sending photo: {e}")
        return None


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    keyboard = [
        [InlineKeyboardButton("  DOWNLOAD MOVIES", callback_data='search_movies')],
        [
            InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
            InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
            InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
        ],
        [InlineKeyboardButton("📈 Popular Movies", callback_data='popular'),
         InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
        [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
        [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_with_warning(
        update.message,
        context,
        f"👋 Hello {user_name}! Welcome to @movieshuba11_bot!\n\nClick on /start to restart or type",
        reply_markup=reply_markup
    )

async def show_start_menu(message, context: ContextTypes.DEFAULT_TYPE):
    # Get user's name from the callback query
    user_name = message._effective_user.first_name if hasattr(message, '_effective_user') else "there"
    keyboard = [
        [InlineKeyboardButton(" Download movies", callback_data='search_movies')],
        [
            InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
            InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
            InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
        ],
        [InlineKeyboardButton("📈 Popular Movies", callback_data='popular')],
        [InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
        [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
        [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_with_warning(
        message,
        context,
        f"👋 Hello {user_name}! Welcome to moviieshubb_bot!\n\nClick on /start to restart or type",
        reply_markup=reply_markup
    )



async def get_random_movies_by_genre(message, context: ContextTypes.DEFAULT_TYPE, genre_id=None):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "sort_by": "popularity.desc",
            "page": 1
        }

        if genre_id:
            params["with_genres"] = genre_id

        response = requests.get(url, params=params)
        response.raise_for_status()
        total_pages = min(response.json().get("total_pages", 1), 500)

        random_page = random.randint(1, total_pages)
        params["page"] = random_page

        response = requests.get(url, params=params)
        response.raise_for_status()

        all_movies = response.json().get("results", [])
        random_movies = random.sample(all_movies, min(5, len(all_movies)))

        response_text = "🎲 Random Movie Suggestions:\n\n"
        keyboard = []
        for i, movie in enumerate(random_movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"
            keyboard.append([InlineKeyboardButton(f"🔍 Search {movie['title']}", callback_data=f'search_specific_{movie["id"]}')])

        keyboard.extend([
            [
                InlineKeyboardButton("👻 Horror", callback_data='random_horror'),
                InlineKeyboardButton("🔪 Crime", callback_data='random_crime'),
                InlineKeyboardButton("💝 Romance", callback_data='random_romance')
            ],
            [InlineKeyboardButton("🎲 More Random", callback_data='random_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching random movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='random_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                                "Sorry, couldn't fetch random movies right now.",
                                reply_markup=reply_markup)


async def get_popular_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/movie/popular"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "🎬 Currently Popular Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching popular movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='popular')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch popular movies right now.",
                              reply_markup=reply_markup)

async def get_horror_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "with_genres": HORROR_GENRE_ID,
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "👻 Popular Horror Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton("👻 More Horror Movies", callback_data='horror_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching horror movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='horror_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch horror movies right now.",
                              reply_markup=reply_markup)

async def get_bollywood_popular_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "region": "IN",
            "with_original_language": "hi",
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "🎬  Bollywood Popular Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching Bollywood movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='bollywood_popular')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch Bollywood movies right now.",
                              reply_markup=reply_markup)


async def search_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    special_case, special_links = special_cases_manager.is_special_case(query)
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Log the search
    search_logger.log_search(user_id, user_name, "movie", query)
    try:
        tmdb_handler = TMDBAPIHandler(TMDB_API_KEY)

        # Search for movie
        results = tmdb_handler.make_request(
            "/search/movie",
            params={"query": query, "language": "en-US"}
        ).get("results", [])

        if results:
            movie = results[0]
            movie_id = movie["id"]

            # Get movie details
            movie_details = tmdb_handler.make_request(f"/movie/{movie_id}")
            providers = tmdb_handler.make_request(f"/movie/{movie_id}/watch/providers").get("results", {}).get("US",
                                                                                                               {}).get(
                "flatrate", [])

        search_url = f"{TMDB_BASE_URL}/search/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        if results:
            movie = results[0]
            movie_id = movie["id"]

            details_url = f"{TMDB_BASE_URL}/movie/{movie_id}"
            watch_providers_url = f"{TMDB_BASE_URL}/movie/{movie_id}/watch/providers"

            details_response = requests.get(details_url, params={"api_key": TMDB_API_KEY})
            providers_response = requests.get(watch_providers_url, params={"api_key": TMDB_API_KEY})

            movie_details = details_response.json()
            providers = providers_response.json().get("results", {}).get("US", {}).get("flatrate", [])

            keyboard = [
                [InlineKeyboardButton(" Search Another Movie", callback_data='search_movies')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            response_text = (
                f"*{movie_details['title']}* ({movie_details.get('release_date', '')[:4]})\n\n"
                f"Plot: {movie_details.get('overview', 'No plot available')}\n\n"
            )

            if providers:
                response_text += "Available on: " + ", ".join(p["provider_name"] for p in providers) + "\n\n"
            else:
                response_text += "Streaming information not available\n\n"

            if special_case and special_links:
                response_text += "Download Links:\n"
                for link in special_links:
                    lang_text = f" ({link['language']})" if link.get('language') else ""
                    response_text += f"• {link['url']}{lang_text}\n"
            else:
                response_text += "download link comming soon msg @balaram129"

            if movie_details.get("poster_path"):
                poster_url = f"{TMDB_IMAGE_BASE_URL}{movie_details['poster_path']}"
                await send_photo_with_warning(update.message, context, photo=poster_url, caption=response_text, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                await send_with_warning(update.message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            keyboard = [
                [InlineKeyboardButton(" Try Again", callback_data='search_movies')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(update.message, context, "No movies found matching your search.", reply_markup=reply_markup)
    except Exception as e:
        print(f"Error in movie search: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(update.message, context,
                              "Sorry, there was an error processing your request. Please try again.",
                              reply_markup=reply_markup)

async def search_by_actor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Log the search
    search_logger.log_search(user_id, user_name, "actor", query)
    try:
        search_url = f"{TMDB_BASE_URL}/search/person"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        if results:
            actor = results[0]
            actor_id = actor["id"]

            actor_details_url = f"{TMDB_BASE_URL}/person/{actor_id}"
            movies_url = f"{TMDB_BASE_URL}/person/{actor_id}/movie_credits"

            actor_details_response = requests.get(actor_details_url, params={"api_key": TMDB_API_KEY})
            movies_response = requests.get(movies_url, params={"api_key": TMDB_API_KEY})

            actor_details = actor_details_response.json()
            movies = movies_response.json().get("cast", [])

            movies_with_rating = [m for m in movies if m.get("vote_average", 0) > 0]
            sorted_movies = sorted(movies_with_rating, key=lambda x: x.get("vote_average", 0), reverse=True)

            popular_movies = [m for m in sorted_movies if m.get("vote_average", 0) >= 7][:4]
            unpopular_movies = [m for m in sorted_movies if m.get("vote_average", 0) < 7][:4]

            response_text = f"🎭 {actor['name']}\n"
            if actor_details.get("birthday"):
                response_text += f"Birthday: {actor_details['birthday']}\n"
            if actor_details.get("place_of_birth"):
                response_text += f"Birthplace: {actor_details['place_of_birth']}\n"

            response_text += "\n📈 Highly Rated Movies:\n"
            for i, movie in enumerate(popular_movies, 1):
                response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
                response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"

            response_text += "\n📉 Other Notable Movies:\n"
            for i, movie in enumerate(unpopular_movies, 1):
                response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
                response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"

            keyboard = [
                [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
                [InlineKeyboardButton(" Search Another Actor", callback_data='search_actor')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            if actor.get("profile_path"):
                actor_image_url = f"{TMDB_IMAGE_BASE_URL}{actor['profile_path']}"
                await send_photo_with_warning(
                    update.message,
                    context,
                    photo=actor_image_url,
                    caption=response_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await send_with_warning(
                    update.message,
                    context,
                    response_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
        else:
            keyboard = [
                [InlineKeyboardButton(" Try Again", callback_data='search_actor')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                update.message,
                context,
                "No actor found matching your search.",
                reply_markup=reply_markup
            )
    except Exception as e:
        print(f"Error in actor search: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='search_actor')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(
            update.message,
            context,
            "Sorry, there was an error processing your request. Please try again.",
            reply_markup=reply_markup
        )
def is_special_case(query):
    query_lower = query.lower().strip()
    for key, case in special_cases_manager.items():
        if query_lower == key.lower() or query_lower in [v.lower() for v in case["variants"]]:
            return True, case["links"]
    return False, []

async def get_genre_movies(message, context: ContextTypes.DEFAULT_TYPE, genre_id: int, genre_name: str):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "with_genres": genre_id,
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = f"🎬 Popular {genre_name} Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching {genre_name} movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data=f'genre_{genre_name.lower()}')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              f"Sorry, couldn't fetch {genre_name} movies right now.",
                              reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_name = query.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    try:
        if query.data.startswith('search_specific_'):
            movie_id = query.data.split('_')[2]
            # Get movie details from TMDB
            url = f"{TMDB_BASE_URL}/movie/{movie_id}"
            response = requests.get(url, params={"api_key": TMDB_API_KEY})
            movie = response.json()

            # Create a message with movie details
            movie_text = f"{movie['title']} ({movie.get('release_date', '')[:4]})"

            # Send a temporary message to user's private chat
            class SimulatedMessage:
                def __init__(self, chat_id, text, from_user):
                    self.chat_id = chat_id
                    self.text = text
                    self.from_user = from_user

                def reply_text(self, *args, **kwargs):
                    return query.message.reply_text(*args, **kwargs)

                def reply_photo(self, *args, **kwargs):
                    return query.message.reply_photo(*args, **kwargs)

            # Create a proper message object
            simulated_message = SimulatedMessage(
                chat_id=query.message.chat_id,
                text=movie['title'],
                from_user=query.from_user
            )

            # Create a proper update object
            class SimulatedUpdate:
                def __init__(self, message):
                    self.message = message

            simulated_update = SimulatedUpdate(simulated_message)

            # Perform the search
            await search_movie(simulated_update, context)
            return
        if query.data == 'genre_horror':
            await get_genre_movies(query.message, context, GENRE_IDS['horror'], "Horror")
        elif query.data == 'genre_romance':
            await get_genre_movies(query.message, context, GENRE_IDS['romance'], "Romance")
        elif query.data == 'genre_crime':
            await get_genre_movies(query.message, context, GENRE_IDS['crime'], "Crime")
        elif query.data == 'random_movies':
            await get_random_movies_by_genre(query.message, context)
        if query.data == 'random_movies':
            await get_random_movies_by_genre(query.message, context)
        elif query.data == 'random_horror':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['horror'])
        elif query.data == 'random_crime':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['crime'])
        elif query.data == 'random_romance':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['romance'])
        elif query.data == 'horror_movies':
            await get_horror_movies(query.message, context)
        elif query.data == 'search_movies':
            USER_CONTEXT[query.message.chat_id] = 'movie'
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "🔍 Just type the name of any movie you want to search for!",
                reply_markup=reply_markup
            )
        elif query.data == 'search_actor':
            USER_CONTEXT[query.message.chat_id] = 'actor'
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "🎭 Just type the name of any actor to see their movies!",
                reply_markup=reply_markup
            )
        elif query.data == 'help':
            help_text = ("📖 How to use this bot:\n\n"
                        "1. Simply type any movie name\n"
                        "2. Or type any actor name to find their movies\n"
                        "3. I'll show you the details\n"
                        "4. Check out popular movies in both Hollywood and Bollywood\n"
                        "5. Try our random movie suggestions by genre!\n"
                        "Need more help? Just type /start to see the main menu again! or msg @balaram129")
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                help_text,
                reply_markup=reply_markup
            )
        elif query.data == 'popular':
            await get_popular_movies(query.message, context)
        elif query.data == 'bollywood_popular':
            await get_bollywood_popular_movies(query.message, context)
        elif query.data == 'start_menu':
            keyboard = [
                [InlineKeyboardButton("🔍 Download movies", callback_data='search_movies'),
                 InlineKeyboardButton("👻 Horror Movies", callback_data='horror_movies')],
                [
                    InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
                    InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
                    InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
                ],
                [InlineKeyboardButton("📈 Popular Movies", callback_data='popular')],
                [InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
                [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
                [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
                [InlineKeyboardButton("❓ Help", callback_data='help')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "👋 Welcome to moviieshubb_bot!\n\nClick on /start to restart or type",
                reply_markup=reply_markup
            )

    except Exception as e:
        print(f"Error in button callback: {e}")
        keyboard = [
            [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(
            query.message,
            context,
            "Sorry, there was an error processing your request. Please try again.",
            reply_markup=reply_markup
        )

async def handle_user_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_context = USER_CONTEXT.get(update.message.chat_id, "movie")
    if user_context == "actor":
        await search_by_actor(update, context)
    else:
        await search_movie(update, context)

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_message_later(context, update.message.chat_id, update.message.message_id)
    await handle_user_query(update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Exception while handling an update: {context.error}")
    if isinstance(context.error, Conflict):
        print("Bot instance already running. Exiting...")
        sys.exit(1)
    elif isinstance(context.error, NetworkError):
        print("Network error occurred. Waiting before retry...")
        await asyncio.sleep(1)
    else:
        print(f"Unexpected error: {context.error}")


def main():
    try:
        application = (
            Application.builder()
            .token(TELEGRAM_TOKEN)
            .build()
        )

        # Add existing handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CallbackQueryHandler(button_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))
        application.add_handler(CommandHandler("viewsearches", view_searches_command))

        # Add error handler
        application.add_error_handler(error_handler)

        # Set up the cleanup job to run every 10 seconds
        job_queue = application.job_queue
        job_queue.run_repeating(cleanup_job, interval=10, first=0)

        # Add the inactive user check job (runs every 6 hours)
        job_queue.run_repeating(check_inactive_users, interval=21600, first=21600)

        # Update stastics more frequently (every 5 minutes)
        job_queue.run_repeating(update_stastics_job, interval=300, first=0)

        # Initial statistics update
        print("Performing initial statistics update...")
        stats = SearchStatistics()
        stats.update_stastics_file()
        print("Initial statistics update completed")

        # Start the bot
        print("Starting bot...")
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

    except Exception as e:
        print(f"Error starting bot: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

# Test the logger
logger = SearchLogger()
logger.log_search(123456, "TestUser", "movie", "Avatar")

# Check recent searches
recent = logger.get_recent_searches()
print("Recent searches:", recent)import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import Conflict, NetworkError, TelegramError
import nest_asyncio
import sys
import random
from typing import Optional, Dict
from datetime import datetime, timedelta
import pickle
from special_cases_managerss import SpecialCasesManager
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import json
from datetime import datetime
from pathlib import Path


class SearchLogger:
    def __init__(self, log_file="search_logs.json"):
        self.log_file = log_file
        self.ensure_log_file_exists()

    def ensure_log_file_exists(self):
        # Create the file with an empty list if it doesn't exist or is empty
        if not Path(self.log_file).exists() or Path(self.log_file).stat().st_size == 0:
            with open(self.log_file, 'w') as f:
                json.dump([], f)

    def log_search(self, user_id: int, user_name: str, search_type: str, search_query: str):
        try:
            # First ensure the file exists and has valid JSON
            self.ensure_log_file_exists()

            # Read existing logs
            try:
                with open(self.log_file, 'r') as f:
                    logs = json.load(f)
            except json.JSONDecodeError:
                # If there's an error reading the JSON, start with an empty list
                logs = []

            # Create new log entry
            log_entry = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "user_id": user_id,
                "user_name": user_name,
                "search_type": search_type,
                "search_query": search_query
            }

            # Add new entry
            logs.append(log_entry)

            # Write back to file
            with open(self.log_file, 'w') as f:
                json.dump(logs, f, indent=2)

        except Exception as e:
            print(f"Error logging search: {e}")

    def get_recent_searches(self, limit: int = 100):
        try:
            # First ensure the file exists and has valid JSON
            self.ensure_log_file_exists()

            with open(self.log_file, 'r') as f:
                try:
                    logs = json.load(f)
                except json.JSONDecodeError:
                    return []
            return logs[-limit:]
        except Exception as e:
            print(f"Error getting recent searches: {e}")
            return []


# Create an instance of the logger
search_logger = SearchLogger()


# After your other global variables
special_cases_manager = SpecialCasesManager()

# Initialize some cases if you want (optional)
special_cases_manager.add_case(
    "pushpa 2",
    ["pushpa2", "pushpa-2", "pushpa2therule", "pushpa 2 the rule"],
    [
        {"url": "https://example4.com", "language": "Hindi"},
        {"url": "https://example5.com", "language": "Telugu"}
    ]
)

special_cases_manager.add_case(
    "venom",
    ["venom", "venom1", "venom2"],
    [
        {"url": "https://www.udlinks.com/3I1l", "language": "hindi"}
    ]
)




nest_asyncio.apply()

TELEGRAM_TOKEN = "7883754025:AAHUDU-_EM4QYome14k_28PQbPTWsl_9w6s"
TMDB_API_KEY = "c3b8704a4df65146c194940351efa9a2"
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
DELETE_TIMEOUT = 420  # 7 minutes in seconds
DISCLAIMER = "⚠️ This message will be deleted in 7 minutes"
HORROR_GENRE_ID = 27  # TMDB's genre ID for horror movies



USER_CONTEXT = {}

GENRE_IDS = {
    'horror': 27,
    'crime': 80,
    'romance': 10749
}


class TMDBAPIHandler:
    def __init__(self, api_key, base_url="https://api.themoviedb.org/3"):
        self.api_key = api_key
        self.base_url = base_url
        self.session = self._create_session()

    def _create_session(self):
        session = requests.Session()

        # Configure retry strategy
        retries = Retry(
            total=5,  # Total number of retries
            backoff_factor=0.5,  # Wait 0.5, 1, 2, 4, 8 seconds between retries
            status_forcelist=[500, 502, 503, 504, 408, 429]  # HTTP status codes to retry on
        )

        # Add retry adapter to session
        adapter = HTTPAdapter(max_retries=retries)
        session.mount('http://', adapter)
        session.mount('https://', adapter)

        return session

    def make_request(self, endpoint, params=None):
        if params is None:
            params = {}

        # Always include API key
        params['api_key'] = self.api_key

        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                response = self.session.get(
                    f"{self.base_url}{endpoint}",
                    params=params,
                    timeout=10  # 10 seconds timeout
                )
                response.raise_for_status()
                return response.json()

            except requests.exceptions.ConnectionError as e:
                if attempt == max_attempts - 1:
                    raise Exception("Unable to connect to TMDB API. Please check your internet connection.") from e
                time.sleep(2 ** attempt)  # Exponential backoff

            except requests.exceptions.Timeout as e:
                if attempt == max_attempts - 1:
                    raise Exception("TMDB API request timed out. Please try again later.") from e
                time.sleep(2 ** attempt)

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:  # Rate limit exceeded
                    retry_after = int(e.response.headers.get('Retry-After', 5))
                    time.sleep(retry_after)
                    continue
                raise Exception(f"TMDB API error: {e.response.status_code}") from e


LAST_ACTIVITY_FILE = "user_activity.pkl"
INACTIVITY_THRESHOLD = timedelta(hours=78)


class SearchStatistics:
    def __init__(self, log_file="search_logs.json", stats_file="stastics.txt"):
        self.log_file = log_file
        self.stats_file = stats_file
        self.search_logger = SearchLogger(log_file)
        # Ensure stastics file exists
        self.update_stastics_file()
        print(f"SearchStatistics initialized. Stats file: {stats_file}")

    def _load_searches(self):
        """Load searches from the log file"""
        try:
            with open(self.log_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def get_most_searched(self, days=None):
        """Get most searched queries within specified days"""
        searches = self._load_searches()
        if not searches:
            return []

        # Filter by date if days is specified
        if days:
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            searches = [s for s in searches if s['timestamp'][:10] >= cutoff_date]

        # Count search queries
        query_counts = {}
        for search in searches:
            query = search['search_query'].lower()
            query_counts[query] = query_counts.get(query, 0) + 1

        # Sort by count and return top 10
        return sorted(query_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    def get_user_search_history(self, limit=50):
        """Get recent user search history"""
        searches = self._load_searches()
        return searches[-limit:] if searches else []

    def update_stastics_file(self):  # Changed method name to match file name
        try:
            print(f"Updating stastics file at {datetime.now()}")

            # Check if log file exists and has data
            if not Path(self.log_file).exists():
                print(f"Log file {self.log_file} does not exist!")
                return

            # Load searches
            searches = self._load_searches()
            if not searches:
                print("No search data found in logs")
                stats_text = "No search data available yet.\nLast Updated: " + datetime.now().strftime(
                    '%Y-%m-%d %H:%M:%S')
            else:
                # Get statistics for different time periods
                all_time = self.get_most_searched()
                today = self.get_most_searched(days=1)
                week = self.get_most_searched(days=7)
                year = self.get_most_searched(days=365)
                user_history = self.get_user_search_history(limit=50)

                stats_text = self._format_stastics(all_time, today, week, year, user_history)  # Changed method name

            # Write to stastics file
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                f.write(stats_text)

            print(f"Stastics file updated successfully at {datetime.now()}")

            # Debug: Read and print file contents
            with open(self.stats_file, 'r', encoding='utf-8') as f:
                content = f.read()
            print(f"Stastics file size: {len(content)} bytes")

        except Exception as e:
            print(f"Error updating stastics file: {e}")
            import traceback
            traceback.print_exc()

    def _format_stastics(self, all_time, today, week, year, user_history):  # Changed method name
        stats_text = "Movie Search Stastics\n"  # Changed heading
        stats_text += "=" * 50 + "\n\n"

        # Add section for each time period
        sections = [
            ("All-Time Most Searched Movies:", all_time),
            ("Today's Most Searched Movies:", today),
            ("This Week's Most Searched Movies:", week),
            ("This Year's Most Searched Movies:", year)
        ]

        for title, data in sections:
            stats_text += f"{title}\n"
            if data:
                stats_text += "\n".join(f"{i + 1}. {movie} ({count} searches)"
                                      for i, (movie, count) in enumerate(data))
            else:
                stats_text += "No searches in this period"
            stats_text += "\n\n"

        # Add user history section
        stats_text += "Recent User Search History:\n"
        stats_text += "=" * 50 + "\n"
        if user_history:
            for search in user_history:
                stats_text += f"\nTime: {search['timestamp']}\n"
                stats_text += f"User: {search['user_name']} (ID: {search['user_id']})\n"
                stats_text += f"Search Type: {search['search_type']}\n"
                stats_text += f"Query: {search['search_query']}\n"
                stats_text += "-" * 30 + "\n"
        else:
            stats_text += "\nNo user search history available yet\n"

        stats_text += f"\nLast Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        return stats_text

# Modify the update_statistics_job to include error handling and logging
async def update_stastics_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        print(f"Starting stastics update job at {datetime.now()}")
        stats = SearchStatistics()
        stats.update_stastics_file()
        print(f"Completed stastics update job at {datetime.now()}")
    except Exception as e:
        print(f"Error in stastics update job: {e}")
        import traceback
        traceback.print_exc()

async def view_searches_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only allow yourself to see the searches
    if update.message.from_user.id == 6822829183:  # Replace with your Telegram ID
        recent_searches = search_logger.get_recent_searches(limit=10)  # Get last 10 searches

        message = "Recent Searches:\n\n"
        for search in recent_searches:
            message += f"👤 User: {search['user_name']}\n"
            message += f"🔍 Query: {search['search_query']}\n"
            message += f"⏰ Time: {search['timestamp']}\n"
            message += f"Type: {search['search_type']}\n\n"

        await update.message.reply_text(message)
    else:
        await update.message.reply_text("You don't have permission to use this command.")


# Add this to your command handlers

class UserActivityManager:
    def __init__(self):
        self.user_activity = {}
        self.load_activity()

    def load_activity(self):
        if Path(LAST_ACTIVITY_FILE).exists():
            try:
                with open(LAST_ACTIVITY_FILE, 'rb') as f:
                    self.user_activity = pickle.load(f)
            except Exception as e:
                print(f"Error loading user activity: {e}")
                self.user_activity = {}

    def save_activity(self):
        try:
            with open(LAST_ACTIVITY_FILE, 'wb') as f:
                pickle.dump(self.user_activity, f)
        except Exception as e:
            print(f"Error saving user activity: {e}")

    def update_user_activity(self, user_id: int, user_name: str):
        self.user_activity[user_id] = {
            'last_active': datetime.now(),
            'name': user_name
        }
        self.save_activity()

    def get_inactive_users(self):
        current_time = datetime.now()
        inactive_users = []

        for user_id, data in self.user_activity.items():
            if (current_time - data['last_active']) >= INACTIVITY_THRESHOLD:
                inactive_users.append({
                    'user_id': user_id,
                    'name': data['name'],
                    'last_active': data['last_active']
                })

        return inactive_users


# Create global instance
activity_manager = UserActivityManager()


# Modify the handle_user_message function to track activity
async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    await delete_message_later(context, update.message.chat_id, update.message.message_id)
    await handle_user_query(update, context)


# Add a new function to check for inactive users
async def check_inactive_users(context: ContextTypes.DEFAULT_TYPE):
    inactive_users = activity_manager.get_inactive_users()

    for user in inactive_users:
        try:
            message = f"Hey {user['name']} 👋,\n\nI am missing you dear! 💫\nIt's been a while since we last chatted. Come back and discover some amazing movies! 🎬"

            await context.bot.send_message(
                chat_id=user['user_id'],
                text=message,
                parse_mode='Markdown'
            )

            # Update the last activity to prevent spam
            activity_manager.update_user_activity(user['user_id'], user['name'])

        except Exception as e:
            print(f"Error sending reminder to user {user['user_id']}: {e}")

class MessageTracker:
    def __init__(self):
        self.messages: Dict[int, Dict[int, datetime]] = {}

    async def add_message(self, chat_id: int, message_id: int):
        if chat_id not in self.messages:
            self.messages[chat_id] = {}
        self.messages[chat_id][message_id] = datetime.now() + timedelta(seconds=DELETE_TIMEOUT)

    async def cleanup_messages(self, context: ContextTypes.DEFAULT_TYPE):
        current_time = datetime.now()
        for chat_id in list(self.messages.keys()):
            for message_id, expiry_time in list(self.messages[chat_id].items()):
                if current_time >= expiry_time:
                    try:
                        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                    except TelegramError:
                        pass  # Message might already be deleted
                    finally:
                        del self.messages[chat_id][message_id]
            if not self.messages[chat_id]:
                del self.messages[chat_id]

message_tracker = MessageTracker()

async def cleanup_job(context: ContextTypes.DEFAULT_TYPE):
    await message_tracker.cleanup_messages(context)

async def delete_message_later(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int):
    await message_tracker.add_message(chat_id, message_id)

async def send_with_warning(message, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None, parse_mode=None):
    try:
        if hasattr(message, 'reply_text'):
            sent_message = await message.reply_text(
                f"{text}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await message.edit_text(
                f"{text}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

        await delete_message_later(context, sent_message.chat_id, sent_message.message_id)
        return sent_message
    except TelegramError as e:
        print(f"Error sending message: {e}")
        return None

async def send_photo_with_warning(message, context: ContextTypes.DEFAULT_TYPE, photo: str, caption: str, reply_markup=None, parse_mode=None):
    try:
        if hasattr(message, 'reply_photo'):
            sent_message = await message.reply_photo(
                photo=photo,
                caption=f"{caption}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await context.bot.send_photo(
                chat_id=message.chat_id,
                photo=photo,
                caption=f"{caption}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

        await delete_message_later(context, sent_message.chat_id, sent_message.message_id)
        return sent_message
    except TelegramError as e:
        print(f"Error sending photo: {e}")
        return None


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    keyboard = [
        [InlineKeyboardButton("  DOWNLOAD MOVIES", callback_data='search_movies')],
        [
            InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
            InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
            InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
        ],
        [InlineKeyboardButton("📈 Popular Movies", callback_data='popular'),
         InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
        [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
        [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_with_warning(
        update.message,
        context,
        f"👋 Hello {user_name}! Welcome to @movieshuba11_bot!\n\nClick on /start to restart or type",
        reply_markup=reply_markup
    )

async def show_start_menu(message, context: ContextTypes.DEFAULT_TYPE):
    # Get user's name from the callback query
    user_name = message._effective_user.first_name if hasattr(message, '_effective_user') else "there"
    keyboard = [
        [InlineKeyboardButton(" Download movies", callback_data='search_movies')],
        [
            InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
            InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
            InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
        ],
        [InlineKeyboardButton("📈 Popular Movies", callback_data='popular')],
        [InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
        [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
        [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_with_warning(
        message,
        context,
        f"👋 Hello {user_name}! Welcome to moviieshubb_bot!\n\nClick on /start to restart or type",
        reply_markup=reply_markup
    )



async def get_random_movies_by_genre(message, context: ContextTypes.DEFAULT_TYPE, genre_id=None):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "sort_by": "popularity.desc",
            "page": 1
        }

        if genre_id:
            params["with_genres"] = genre_id

        response = requests.get(url, params=params)
        response.raise_for_status()
        total_pages = min(response.json().get("total_pages", 1), 500)

        random_page = random.randint(1, total_pages)
        params["page"] = random_page

        response = requests.get(url, params=params)
        response.raise_for_status()

        all_movies = response.json().get("results", [])
        random_movies = random.sample(all_movies, min(5, len(all_movies)))

        response_text = "🎲 Random Movie Suggestions:\n\n"
        keyboard = []
        for i, movie in enumerate(random_movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"
            keyboard.append([InlineKeyboardButton(f"🔍 Search {movie['title']}", callback_data=f'search_specific_{movie["id"]}')])

        keyboard.extend([
            [
                InlineKeyboardButton("👻 Horror", callback_data='random_horror'),
                InlineKeyboardButton("🔪 Crime", callback_data='random_crime'),
                InlineKeyboardButton("💝 Romance", callback_data='random_romance')
            ],
            [InlineKeyboardButton("🎲 More Random", callback_data='random_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching random movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='random_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                                "Sorry, couldn't fetch random movies right now.",
                                reply_markup=reply_markup)


async def get_popular_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/movie/popular"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "🎬 Currently Popular Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching popular movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='popular')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch popular movies right now.",
                              reply_markup=reply_markup)

async def get_horror_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "with_genres": HORROR_GENRE_ID,
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "👻 Popular Horror Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton("👻 More Horror Movies", callback_data='horror_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching horror movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='horror_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch horror movies right now.",
                              reply_markup=reply_markup)

async def get_bollywood_popular_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "region": "IN",
            "with_original_language": "hi",
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "🎬  Bollywood Popular Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching Bollywood movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='bollywood_popular')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch Bollywood movies right now.",
                              reply_markup=reply_markup)


async def search_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    special_case, special_links = special_cases_manager.is_special_case(query)
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Log the search
    search_logger.log_search(user_id, user_name, "movie", query)
    try:
        tmdb_handler = TMDBAPIHandler(TMDB_API_KEY)

        # Search for movie
        results = tmdb_handler.make_request(
            "/search/movie",
            params={"query": query, "language": "en-US"}
        ).get("results", [])

        if results:
            movie = results[0]
            movie_id = movie["id"]

            # Get movie details
            movie_details = tmdb_handler.make_request(f"/movie/{movie_id}")
            providers = tmdb_handler.make_request(f"/movie/{movie_id}/watch/providers").get("results", {}).get("US",
                                                                                                               {}).get(
                "flatrate", [])

        search_url = f"{TMDB_BASE_URL}/search/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        if results:
            movie = results[0]
            movie_id = movie["id"]

            details_url = f"{TMDB_BASE_URL}/movie/{movie_id}"
            watch_providers_url = f"{TMDB_BASE_URL}/movie/{movie_id}/watch/providers"

            details_response = requests.get(details_url, params={"api_key": TMDB_API_KEY})
            providers_response = requests.get(watch_providers_url, params={"api_key": TMDB_API_KEY})

            movie_details = details_response.json()
            providers = providers_response.json().get("results", {}).get("US", {}).get("flatrate", [])

            keyboard = [
                [InlineKeyboardButton(" Search Another Movie", callback_data='search_movies')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            response_text = (
                f"*{movie_details['title']}* ({movie_details.get('release_date', '')[:4]})\n\n"
                f"Plot: {movie_details.get('overview', 'No plot available')}\n\n"
            )

            if providers:
                response_text += "Available on: " + ", ".join(p["provider_name"] for p in providers) + "\n\n"
            else:
                response_text += "Streaming information not available\n\n"

            if special_case and special_links:
                response_text += "Download Links:\n"
                for link in special_links:
                    lang_text = f" ({link['language']})" if link.get('language') else ""
                    response_text += f"• {link['url']}{lang_text}\n"
            else:
                response_text += "download link comming soon msg @balaram129"

            if movie_details.get("poster_path"):
                poster_url = f"{TMDB_IMAGE_BASE_URL}{movie_details['poster_path']}"
                await send_photo_with_warning(update.message, context, photo=poster_url, caption=response_text, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                await send_with_warning(update.message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            keyboard = [
                [InlineKeyboardButton(" Try Again", callback_data='search_movies')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(update.message, context, "No movies found matching your search.", reply_markup=reply_markup)
    except Exception as e:
        print(f"Error in movie search: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(update.message, context,
                              "Sorry, there was an error processing your request. Please try again.",
                              reply_markup=reply_markup)

async def search_by_actor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Log the search
    search_logger.log_search(user_id, user_name, "actor", query)
    try:
        search_url = f"{TMDB_BASE_URL}/search/person"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        if results:
            actor = results[0]
            actor_id = actor["id"]

            actor_details_url = f"{TMDB_BASE_URL}/person/{actor_id}"
            movies_url = f"{TMDB_BASE_URL}/person/{actor_id}/movie_credits"

            actor_details_response = requests.get(actor_details_url, params={"api_key": TMDB_API_KEY})
            movies_response = requests.get(movies_url, params={"api_key": TMDB_API_KEY})

            actor_details = actor_details_response.json()
            movies = movies_response.json().get("cast", [])

            movies_with_rating = [m for m in movies if m.get("vote_average", 0) > 0]
            sorted_movies = sorted(movies_with_rating, key=lambda x: x.get("vote_average", 0), reverse=True)

            popular_movies = [m for m in sorted_movies if m.get("vote_average", 0) >= 7][:4]
            unpopular_movies = [m for m in sorted_movies if m.get("vote_average", 0) < 7][:4]

            response_text = f"🎭 {actor['name']}\n"
            if actor_details.get("birthday"):
                response_text += f"Birthday: {actor_details['birthday']}\n"
            if actor_details.get("place_of_birth"):
                response_text += f"Birthplace: {actor_details['place_of_birth']}\n"

            response_text += "\n📈 Highly Rated Movies:\n"
            for i, movie in enumerate(popular_movies, 1):
                response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
                response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"

            response_text += "\n📉 Other Notable Movies:\n"
            for i, movie in enumerate(unpopular_movies, 1):
                response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
                response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"

            keyboard = [
                [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
                [InlineKeyboardButton(" Search Another Actor", callback_data='search_actor')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            if actor.get("profile_path"):
                actor_image_url = f"{TMDB_IMAGE_BASE_URL}{actor['profile_path']}"
                await send_photo_with_warning(
                    update.message,
                    context,
                    photo=actor_image_url,
                    caption=response_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await send_with_warning(
                    update.message,
                    context,
                    response_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
        else:
            keyboard = [
                [InlineKeyboardButton(" Try Again", callback_data='search_actor')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                update.message,
                context,
                "No actor found matching your search.",
                reply_markup=reply_markup
            )
    except Exception as e:
        print(f"Error in actor search: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='search_actor')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(
            update.message,
            context,
            "Sorry, there was an error processing your request. Please try again.",
            reply_markup=reply_markup
        )
def is_special_case(query):
    query_lower = query.lower().strip()
    for key, case in special_cases_manager.items():
        if query_lower == key.lower() or query_lower in [v.lower() for v in case["variants"]]:
            return True, case["links"]
    return False, []

async def get_genre_movies(message, context: ContextTypes.DEFAULT_TYPE, genre_id: int, genre_name: str):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "with_genres": genre_id,
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = f"🎬 Popular {genre_name} Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching {genre_name} movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data=f'genre_{genre_name.lower()}')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              f"Sorry, couldn't fetch {genre_name} movies right now.",
                              reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_name = query.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    try:
        if query.data.startswith('search_specific_'):
            movie_id = query.data.split('_')[2]
            # Get movie details from TMDB
            url = f"{TMDB_BASE_URL}/movie/{movie_id}"
            response = requests.get(url, params={"api_key": TMDB_API_KEY})
            movie = response.json()

            # Create a message with movie details
            movie_text = f"{movie['title']} ({movie.get('release_date', '')[:4]})"

            # Send a temporary message to user's private chat
            class SimulatedMessage:
                def __init__(self, chat_id, text, from_user):
                    self.chat_id = chat_id
                    self.text = text
                    self.from_user = from_user

                def reply_text(self, *args, **kwargs):
                    return query.message.reply_text(*args, **kwargs)

                def reply_photo(self, *args, **kwargs):
                    return query.message.reply_photo(*args, **kwargs)

            # Create a proper message object
            simulated_message = SimulatedMessage(
                chat_id=query.message.chat_id,
                text=movie['title'],
                from_user=query.from_user
            )

            # Create a proper update object
            class SimulatedUpdate:
                def __init__(self, message):
                    self.message = message

            simulated_update = SimulatedUpdate(simulated_message)

            # Perform the search
            await search_movie(simulated_update, context)
            return
        if query.data == 'genre_horror':
            await get_genre_movies(query.message, context, GENRE_IDS['horror'], "Horror")
        elif query.data == 'genre_romance':
            await get_genre_movies(query.message, context, GENRE_IDS['romance'], "Romance")
        elif query.data == 'genre_crime':
            await get_genre_movies(query.message, context, GENRE_IDS['crime'], "Crime")
        elif query.data == 'random_movies':
            await get_random_movies_by_genre(query.message, context)
        if query.data == 'random_movies':
            await get_random_movies_by_genre(query.message, context)
        elif query.data == 'random_horror':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['horror'])
        elif query.data == 'random_crime':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['crime'])
        elif query.data == 'random_romance':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['romance'])
        elif query.data == 'horror_movies':
            await get_horror_movies(query.message, context)
        elif query.data == 'search_movies':
            USER_CONTEXT[query.message.chat_id] = 'movie'
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "🔍 Just type the name of any movie you want to search for!",
                reply_markup=reply_markup
            )
        elif query.data == 'search_actor':
            USER_CONTEXT[query.message.chat_id] = 'actor'
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "🎭 Just type the name of any actor to see their movies!",
                reply_markup=reply_markup
            )
        elif query.data == 'help':
            help_text = ("📖 How to use this bot:\n\n"
                        "1. Simply type any movie name\n"
                        "2. Or type any actor name to find their movies\n"
                        "3. I'll show you the details\n"
                        "4. Check out popular movies in both Hollywood and Bollywood\n"
                        "5. Try our random movie suggestions by genre!\n"
                        "Need more help? Just type /start to see the main menu again! or msg @balaram129")
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                help_text,
                reply_markup=reply_markup
            )
        elif query.data == 'popular':
            await get_popular_movies(query.message, context)
        elif query.data == 'bollywood_popular':
            await get_bollywood_popular_movies(query.message, context)
        elif query.data == 'start_menu':
            keyboard = [
                [InlineKeyboardButton("🔍 Download movies", callback_data='search_movies'),
                 InlineKeyboardButton("👻 Horror Movies", callback_data='horror_movies')],
                [
                    InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
                    InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
                    InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
                ],
                [InlineKeyboardButton("📈 Popular Movies", callback_data='popular')],
                [InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
                [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
                [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
                [InlineKeyboardButton("❓ Help", callback_data='help')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "👋 Welcome to moviieshubb_bot!\n\nClick on /start to restart or type",
                reply_markup=reply_markup
            )

    except Exception as e:
        print(f"Error in button callback: {e}")
        keyboard = [
            [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(
            query.message,
            context,
            "Sorry, there was an error processing your request. Please try again.",
            reply_markup=reply_markup
        )

async def handle_user_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_context = USER_CONTEXT.get(update.message.chat_id, "movie")
    if user_context == "actor":
        await search_by_actor(update, context)
    else:
        await search_movie(update, context)

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_message_later(context, update.message.chat_id, update.message.message_id)
    await handle_user_query(update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Exception while handling an update: {context.error}")
    if isinstance(context.error, Conflict):
        print("Bot instance already running. Exiting...")
        sys.exit(1)
    elif isinstance(context.error, NetworkError):
        print("Network error occurred. Waiting before retry...")
        await asyncio.sleep(1)
    else:
        print(f"Unexpected error: {context.error}")


def main():
    try:
        application = (
            Application.builder()
            .token(TELEGRAM_TOKEN)
            .build()
        )

        # Add existing handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CallbackQueryHandler(button_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))
        application.add_handler(CommandHandler("viewsearches", view_searches_command))

        # Add error handler
        application.add_error_handler(error_handler)

        # Set up the cleanup job to run every 10 seconds
        job_queue = application.job_queue
        job_queue.run_repeating(cleanup_job, interval=10, first=0)

        # Add the inactive user check job (runs every 6 hours)
        job_queue.run_repeating(check_inactive_users, interval=21600, first=21600)

        # Update stastics more frequently (every 5 minutes)
        job_queue.run_repeating(update_stastics_job, interval=300, first=0)

        # Initial statistics update
        print("Performing initial statistics update...")
        stats = SearchStatistics()
        stats.update_stastics_file()
        print("Initial statistics update completed")

        # Start the bot
        print("Starting bot...")
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

    except Exception as e:
        print(f"Error starting bot: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

# Test the logger
logger = SearchLogger()
logger.log_search(123456, "TestUser", "movie", "Avatar")

# Check recent searches
recent = logger.get_recent_searches()
print("Recent searches:", recent)import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import Conflict, NetworkError, TelegramError
import nest_asyncio
import sys
import random
from typing import Optional, Dict
from datetime import datetime, timedelta
import pickle
from special_cases_managerss import SpecialCasesManager
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import json
from datetime import datetime
from pathlib import Path


class SearchLogger:
    def __init__(self, log_file="search_logs.json"):
        self.log_file = log_file
        self.ensure_log_file_exists()

    def ensure_log_file_exists(self):
        # Create the file with an empty list if it doesn't exist or is empty
        if not Path(self.log_file).exists() or Path(self.log_file).stat().st_size == 0:
            with open(self.log_file, 'w') as f:
                json.dump([], f)

    def log_search(self, user_id: int, user_name: str, search_type: str, search_query: str):
        try:
            # First ensure the file exists and has valid JSON
            self.ensure_log_file_exists()

            # Read existing logs
            try:
                with open(self.log_file, 'r') as f:
                    logs = json.load(f)
            except json.JSONDecodeError:
                # If there's an error reading the JSON, start with an empty list
                logs = []

            # Create new log entry
            log_entry = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "user_id": user_id,
                "user_name": user_name,
                "search_type": search_type,
                "search_query": search_query
            }

            # Add new entry
            logs.append(log_entry)

            # Write back to file
            with open(self.log_file, 'w') as f:
                json.dump(logs, f, indent=2)

        except Exception as e:
            print(f"Error logging search: {e}")

    def get_recent_searches(self, limit: int = 100):
        try:
            # First ensure the file exists and has valid JSON
            self.ensure_log_file_exists()

            with open(self.log_file, 'r') as f:
                try:
                    logs = json.load(f)
                except json.JSONDecodeError:
                    return []
            return logs[-limit:]
        except Exception as e:
            print(f"Error getting recent searches: {e}")
            return []


# Create an instance of the logger
search_logger = SearchLogger()


# After your other global variables
special_cases_manager = SpecialCasesManager()

# Initialize some cases if you want (optional)
special_cases_manager.add_case(
    "pushpa 2",
    ["pushpa2", "pushpa-2", "pushpa2therule", "pushpa 2 the rule"],
    [
        {"url": "https://example4.com", "language": "Hindi"},
        {"url": "https://example5.com", "language": "Telugu"}
    ]
)

special_cases_manager.add_case(
    "venom",
    ["venom", "venom1", "venom2"],
    [
        {"url": "https://www.udlinks.com/3I1l", "language": "hindi"}
    ]
)




nest_asyncio.apply()

TELEGRAM_TOKEN = "7883754025:AAHUDU-_EM4QYome14k_28PQbPTWsl_9w6s"
TMDB_API_KEY = "c3b8704a4df65146c194940351efa9a2"
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
DELETE_TIMEOUT = 420  # 7 minutes in seconds
DISCLAIMER = "⚠️ This message will be deleted in 7 minutes"
HORROR_GENRE_ID = 27  # TMDB's genre ID for horror movies



USER_CONTEXT = {}

GENRE_IDS = {
    'horror': 27,
    'crime': 80,
    'romance': 10749
}


class TMDBAPIHandler:
    def __init__(self, api_key, base_url="https://api.themoviedb.org/3"):
        self.api_key = api_key
        self.base_url = base_url
        self.session = self._create_session()

    def _create_session(self):
        session = requests.Session()

        # Configure retry strategy
        retries = Retry(
            total=5,  # Total number of retries
            backoff_factor=0.5,  # Wait 0.5, 1, 2, 4, 8 seconds between retries
            status_forcelist=[500, 502, 503, 504, 408, 429]  # HTTP status codes to retry on
        )

        # Add retry adapter to session
        adapter = HTTPAdapter(max_retries=retries)
        session.mount('http://', adapter)
        session.mount('https://', adapter)

        return session

    def make_request(self, endpoint, params=None):
        if params is None:
            params = {}

        # Always include API key
        params['api_key'] = self.api_key

        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                response = self.session.get(
                    f"{self.base_url}{endpoint}",
                    params=params,
                    timeout=10  # 10 seconds timeout
                )
                response.raise_for_status()
                return response.json()

            except requests.exceptions.ConnectionError as e:
                if attempt == max_attempts - 1:
                    raise Exception("Unable to connect to TMDB API. Please check your internet connection.") from e
                time.sleep(2 ** attempt)  # Exponential backoff

            except requests.exceptions.Timeout as e:
                if attempt == max_attempts - 1:
                    raise Exception("TMDB API request timed out. Please try again later.") from e
                time.sleep(2 ** attempt)

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:  # Rate limit exceeded
                    retry_after = int(e.response.headers.get('Retry-After', 5))
                    time.sleep(retry_after)
                    continue
                raise Exception(f"TMDB API error: {e.response.status_code}") from e


LAST_ACTIVITY_FILE = "user_activity.pkl"
INACTIVITY_THRESHOLD = timedelta(hours=78)


class SearchStatistics:
    def __init__(self, log_file="search_logs.json", stats_file="stastics.txt"):
        self.log_file = log_file
        self.stats_file = stats_file
        self.search_logger = SearchLogger(log_file)
        # Ensure stastics file exists
        self.update_stastics_file()
        print(f"SearchStatistics initialized. Stats file: {stats_file}")

    def _load_searches(self):
        """Load searches from the log file"""
        try:
            with open(self.log_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def get_most_searched(self, days=None):
        """Get most searched queries within specified days"""
        searches = self._load_searches()
        if not searches:
            return []

        # Filter by date if days is specified
        if days:
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            searches = [s for s in searches if s['timestamp'][:10] >= cutoff_date]

        # Count search queries
        query_counts = {}
        for search in searches:
            query = search['search_query'].lower()
            query_counts[query] = query_counts.get(query, 0) + 1

        # Sort by count and return top 10
        return sorted(query_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    def get_user_search_history(self, limit=50):
        """Get recent user search history"""
        searches = self._load_searches()
        return searches[-limit:] if searches else []

    def update_stastics_file(self):  # Changed method name to match file name
        try:
            print(f"Updating stastics file at {datetime.now()}")

            # Check if log file exists and has data
            if not Path(self.log_file).exists():
                print(f"Log file {self.log_file} does not exist!")
                return

            # Load searches
            searches = self._load_searches()
            if not searches:
                print("No search data found in logs")
                stats_text = "No search data available yet.\nLast Updated: " + datetime.now().strftime(
                    '%Y-%m-%d %H:%M:%S')
            else:
                # Get statistics for different time periods
                all_time = self.get_most_searched()
                today = self.get_most_searched(days=1)
                week = self.get_most_searched(days=7)
                year = self.get_most_searched(days=365)
                user_history = self.get_user_search_history(limit=50)

                stats_text = self._format_stastics(all_time, today, week, year, user_history)  # Changed method name

            # Write to stastics file
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                f.write(stats_text)

            print(f"Stastics file updated successfully at {datetime.now()}")

            # Debug: Read and print file contents
            with open(self.stats_file, 'r', encoding='utf-8') as f:
                content = f.read()
            print(f"Stastics file size: {len(content)} bytes")

        except Exception as e:
            print(f"Error updating stastics file: {e}")
            import traceback
            traceback.print_exc()

    def _format_stastics(self, all_time, today, week, year, user_history):  # Changed method name
        stats_text = "Movie Search Stastics\n"  # Changed heading
        stats_text += "=" * 50 + "\n\n"

        # Add section for each time period
        sections = [
            ("All-Time Most Searched Movies:", all_time),
            ("Today's Most Searched Movies:", today),
            ("This Week's Most Searched Movies:", week),
            ("This Year's Most Searched Movies:", year)
        ]

        for title, data in sections:
            stats_text += f"{title}\n"
            if data:
                stats_text += "\n".join(f"{i + 1}. {movie} ({count} searches)"
                                      for i, (movie, count) in enumerate(data))
            else:
                stats_text += "No searches in this period"
            stats_text += "\n\n"

        # Add user history section
        stats_text += "Recent User Search History:\n"
        stats_text += "=" * 50 + "\n"
        if user_history:
            for search in user_history:
                stats_text += f"\nTime: {search['timestamp']}\n"
                stats_text += f"User: {search['user_name']} (ID: {search['user_id']})\n"
                stats_text += f"Search Type: {search['search_type']}\n"
                stats_text += f"Query: {search['search_query']}\n"
                stats_text += "-" * 30 + "\n"
        else:
            stats_text += "\nNo user search history available yet\n"

        stats_text += f"\nLast Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        return stats_text

# Modify the update_statistics_job to include error handling and logging
async def update_stastics_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        print(f"Starting stastics update job at {datetime.now()}")
        stats = SearchStatistics()
        stats.update_stastics_file()
        print(f"Completed stastics update job at {datetime.now()}")
    except Exception as e:
        print(f"Error in stastics update job: {e}")
        import traceback
        traceback.print_exc()

async def view_searches_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only allow yourself to see the searches
    if update.message.from_user.id == 6822829183:  # Replace with your Telegram ID
        recent_searches = search_logger.get_recent_searches(limit=10)  # Get last 10 searches

        message = "Recent Searches:\n\n"
        for search in recent_searches:
            message += f"👤 User: {search['user_name']}\n"
            message += f"🔍 Query: {search['search_query']}\n"
            message += f"⏰ Time: {search['timestamp']}\n"
            message += f"Type: {search['search_type']}\n\n"

        await update.message.reply_text(message)
    else:
        await update.message.reply_text("You don't have permission to use this command.")


# Add this to your command handlers

class UserActivityManager:
    def __init__(self):
        self.user_activity = {}
        self.load_activity()

    def load_activity(self):
        if Path(LAST_ACTIVITY_FILE).exists():
            try:
                with open(LAST_ACTIVITY_FILE, 'rb') as f:
                    self.user_activity = pickle.load(f)
            except Exception as e:
                print(f"Error loading user activity: {e}")
                self.user_activity = {}

    def save_activity(self):
        try:
            with open(LAST_ACTIVITY_FILE, 'wb') as f:
                pickle.dump(self.user_activity, f)
        except Exception as e:
            print(f"Error saving user activity: {e}")

    def update_user_activity(self, user_id: int, user_name: str):
        self.user_activity[user_id] = {
            'last_active': datetime.now(),
            'name': user_name
        }
        self.save_activity()

    def get_inactive_users(self):
        current_time = datetime.now()
        inactive_users = []

        for user_id, data in self.user_activity.items():
            if (current_time - data['last_active']) >= INACTIVITY_THRESHOLD:
                inactive_users.append({
                    'user_id': user_id,
                    'name': data['name'],
                    'last_active': data['last_active']
                })

        return inactive_users


# Create global instance
activity_manager = UserActivityManager()


# Modify the handle_user_message function to track activity
async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    await delete_message_later(context, update.message.chat_id, update.message.message_id)
    await handle_user_query(update, context)


# Add a new function to check for inactive users
async def check_inactive_users(context: ContextTypes.DEFAULT_TYPE):
    inactive_users = activity_manager.get_inactive_users()

    for user in inactive_users:
        try:
            message = f"Hey {user['name']} 👋,\n\nI am missing you dear! 💫\nIt's been a while since we last chatted. Come back and discover some amazing movies! 🎬"

            await context.bot.send_message(
                chat_id=user['user_id'],
                text=message,
                parse_mode='Markdown'
            )

            # Update the last activity to prevent spam
            activity_manager.update_user_activity(user['user_id'], user['name'])

        except Exception as e:
            print(f"Error sending reminder to user {user['user_id']}: {e}")

class MessageTracker:
    def __init__(self):
        self.messages: Dict[int, Dict[int, datetime]] = {}

    async def add_message(self, chat_id: int, message_id: int):
        if chat_id not in self.messages:
            self.messages[chat_id] = {}
        self.messages[chat_id][message_id] = datetime.now() + timedelta(seconds=DELETE_TIMEOUT)

    async def cleanup_messages(self, context: ContextTypes.DEFAULT_TYPE):
        current_time = datetime.now()
        for chat_id in list(self.messages.keys()):
            for message_id, expiry_time in list(self.messages[chat_id].items()):
                if current_time >= expiry_time:
                    try:
                        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                    except TelegramError:
                        pass  # Message might already be deleted
                    finally:
                        del self.messages[chat_id][message_id]
            if not self.messages[chat_id]:
                del self.messages[chat_id]

message_tracker = MessageTracker()

async def cleanup_job(context: ContextTypes.DEFAULT_TYPE):
    await message_tracker.cleanup_messages(context)

async def delete_message_later(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int):
    await message_tracker.add_message(chat_id, message_id)

async def send_with_warning(message, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None, parse_mode=None):
    try:
        if hasattr(message, 'reply_text'):
            sent_message = await message.reply_text(
                f"{text}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await message.edit_text(
                f"{text}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

        await delete_message_later(context, sent_message.chat_id, sent_message.message_id)
        return sent_message
    except TelegramError as e:
        print(f"Error sending message: {e}")
        return None

async def send_photo_with_warning(message, context: ContextTypes.DEFAULT_TYPE, photo: str, caption: str, reply_markup=None, parse_mode=None):
    try:
        if hasattr(message, 'reply_photo'):
            sent_message = await message.reply_photo(
                photo=photo,
                caption=f"{caption}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await context.bot.send_photo(
                chat_id=message.chat_id,
                photo=photo,
                caption=f"{caption}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

        await delete_message_later(context, sent_message.chat_id, sent_message.message_id)
        return sent_message
    except TelegramError as e:
        print(f"Error sending photo: {e}")
        return None


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    keyboard = [
        [InlineKeyboardButton("  DOWNLOAD MOVIES", callback_data='search_movies')],
        [
            InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
            InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
            InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
        ],
        [InlineKeyboardButton("📈 Popular Movies", callback_data='popular'),
         InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
        [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
        [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_with_warning(
        update.message,
        context,
        f"👋 Hello {user_name}! Welcome to @movieshuba11_bot!\n\nClick on /start to restart or type",
        reply_markup=reply_markup
    )

async def show_start_menu(message, context: ContextTypes.DEFAULT_TYPE):
    # Get user's name from the callback query
    user_name = message._effective_user.first_name if hasattr(message, '_effective_user') else "there"
    keyboard = [
        [InlineKeyboardButton(" Download movies", callback_data='search_movies')],
        [
            InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
            InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
            InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
        ],
        [InlineKeyboardButton("📈 Popular Movies", callback_data='popular')],
        [InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
        [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
        [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_with_warning(
        message,
        context,
        f"👋 Hello {user_name}! Welcome to moviieshubb_bot!\n\nClick on /start to restart or type",
        reply_markup=reply_markup
    )



async def get_random_movies_by_genre(message, context: ContextTypes.DEFAULT_TYPE, genre_id=None):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "sort_by": "popularity.desc",
            "page": 1
        }

        if genre_id:
            params["with_genres"] = genre_id

        response = requests.get(url, params=params)
        response.raise_for_status()
        total_pages = min(response.json().get("total_pages", 1), 500)

        random_page = random.randint(1, total_pages)
        params["page"] = random_page

        response = requests.get(url, params=params)
        response.raise_for_status()

        all_movies = response.json().get("results", [])
        random_movies = random.sample(all_movies, min(5, len(all_movies)))

        response_text = "🎲 Random Movie Suggestions:\n\n"
        keyboard = []
        for i, movie in enumerate(random_movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"
            keyboard.append([InlineKeyboardButton(f"🔍 Search {movie['title']}", callback_data=f'search_specific_{movie["id"]}')])

        keyboard.extend([
            [
                InlineKeyboardButton("👻 Horror", callback_data='random_horror'),
                InlineKeyboardButton("🔪 Crime", callback_data='random_crime'),
                InlineKeyboardButton("💝 Romance", callback_data='random_romance')
            ],
            [InlineKeyboardButton("🎲 More Random", callback_data='random_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching random movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='random_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                                "Sorry, couldn't fetch random movies right now.",
                                reply_markup=reply_markup)


async def get_popular_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/movie/popular"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "🎬 Currently Popular Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching popular movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='popular')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch popular movies right now.",
                              reply_markup=reply_markup)

async def get_horror_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "with_genres": HORROR_GENRE_ID,
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "👻 Popular Horror Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton("👻 More Horror Movies", callback_data='horror_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching horror movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='horror_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch horror movies right now.",
                              reply_markup=reply_markup)

async def get_bollywood_popular_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "region": "IN",
            "with_original_language": "hi",
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "🎬  Bollywood Popular Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching Bollywood movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='bollywood_popular')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch Bollywood movies right now.",
                              reply_markup=reply_markup)


async def search_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    special_case, special_links = special_cases_manager.is_special_case(query)
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Log the search
    search_logger.log_search(user_id, user_name, "movie", query)
    try:
        tmdb_handler = TMDBAPIHandler(TMDB_API_KEY)

        # Search for movie
        results = tmdb_handler.make_request(
            "/search/movie",
            params={"query": query, "language": "en-US"}
        ).get("results", [])

        if results:
            movie = results[0]
            movie_id = movie["id"]

            # Get movie details
            movie_details = tmdb_handler.make_request(f"/movie/{movie_id}")
            providers = tmdb_handler.make_request(f"/movie/{movie_id}/watch/providers").get("results", {}).get("US",
                                                                                                               {}).get(
                "flatrate", [])

        search_url = f"{TMDB_BASE_URL}/search/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        if results:
            movie = results[0]
            movie_id = movie["id"]

            details_url = f"{TMDB_BASE_URL}/movie/{movie_id}"
            watch_providers_url = f"{TMDB_BASE_URL}/movie/{movie_id}/watch/providers"

            details_response = requests.get(details_url, params={"api_key": TMDB_API_KEY})
            providers_response = requests.get(watch_providers_url, params={"api_key": TMDB_API_KEY})

            movie_details = details_response.json()
            providers = providers_response.json().get("results", {}).get("US", {}).get("flatrate", [])

            keyboard = [
                [InlineKeyboardButton(" Search Another Movie", callback_data='search_movies')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            response_text = (
                f"*{movie_details['title']}* ({movie_details.get('release_date', '')[:4]})\n\n"
                f"Plot: {movie_details.get('overview', 'No plot available')}\n\n"
            )

            if providers:
                response_text += "Available on: " + ", ".join(p["provider_name"] for p in providers) + "\n\n"
            else:
                response_text += "Streaming information not available\n\n"

            if special_case and special_links:
                response_text += "Download Links:\n"
                for link in special_links:
                    lang_text = f" ({link['language']})" if link.get('language') else ""
                    response_text += f"• {link['url']}{lang_text}\n"
            else:
                response_text += "download link comming soon msg @balaram129"

            if movie_details.get("poster_path"):
                poster_url = f"{TMDB_IMAGE_BASE_URL}{movie_details['poster_path']}"
                await send_photo_with_warning(update.message, context, photo=poster_url, caption=response_text, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                await send_with_warning(update.message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            keyboard = [
                [InlineKeyboardButton(" Try Again", callback_data='search_movies')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(update.message, context, "No movies found matching your search.", reply_markup=reply_markup)
    except Exception as e:
        print(f"Error in movie search: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(update.message, context,
                              "Sorry, there was an error processing your request. Please try again.",
                              reply_markup=reply_markup)

async def search_by_actor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Log the search
    search_logger.log_search(user_id, user_name, "actor", query)
    try:
        search_url = f"{TMDB_BASE_URL}/search/person"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        if results:
            actor = results[0]
            actor_id = actor["id"]

            actor_details_url = f"{TMDB_BASE_URL}/person/{actor_id}"
            movies_url = f"{TMDB_BASE_URL}/person/{actor_id}/movie_credits"

            actor_details_response = requests.get(actor_details_url, params={"api_key": TMDB_API_KEY})
            movies_response = requests.get(movies_url, params={"api_key": TMDB_API_KEY})

            actor_details = actor_details_response.json()
            movies = movies_response.json().get("cast", [])

            movies_with_rating = [m for m in movies if m.get("vote_average", 0) > 0]
            sorted_movies = sorted(movies_with_rating, key=lambda x: x.get("vote_average", 0), reverse=True)

            popular_movies = [m for m in sorted_movies if m.get("vote_average", 0) >= 7][:4]
            unpopular_movies = [m for m in sorted_movies if m.get("vote_average", 0) < 7][:4]

            response_text = f"🎭 {actor['name']}\n"
            if actor_details.get("birthday"):
                response_text += f"Birthday: {actor_details['birthday']}\n"
            if actor_details.get("place_of_birth"):
                response_text += f"Birthplace: {actor_details['place_of_birth']}\n"

            response_text += "\n📈 Highly Rated Movies:\n"
            for i, movie in enumerate(popular_movies, 1):
                response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
                response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"

            response_text += "\n📉 Other Notable Movies:\n"
            for i, movie in enumerate(unpopular_movies, 1):
                response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
                response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"

            keyboard = [
                [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
                [InlineKeyboardButton(" Search Another Actor", callback_data='search_actor')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            if actor.get("profile_path"):
                actor_image_url = f"{TMDB_IMAGE_BASE_URL}{actor['profile_path']}"
                await send_photo_with_warning(
                    update.message,
                    context,
                    photo=actor_image_url,
                    caption=response_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await send_with_warning(
                    update.message,
                    context,
                    response_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
        else:
            keyboard = [
                [InlineKeyboardButton(" Try Again", callback_data='search_actor')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                update.message,
                context,
                "No actor found matching your search.",
                reply_markup=reply_markup
            )
    except Exception as e:
        print(f"Error in actor search: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='search_actor')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(
            update.message,
            context,
            "Sorry, there was an error processing your request. Please try again.",
            reply_markup=reply_markup
        )
def is_special_case(query):
    query_lower = query.lower().strip()
    for key, case in special_cases_manager.items():
        if query_lower == key.lower() or query_lower in [v.lower() for v in case["variants"]]:
            return True, case["links"]
    return False, []

async def get_genre_movies(message, context: ContextTypes.DEFAULT_TYPE, genre_id: int, genre_name: str):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "with_genres": genre_id,
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = f"🎬 Popular {genre_name} Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching {genre_name} movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data=f'genre_{genre_name.lower()}')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              f"Sorry, couldn't fetch {genre_name} movies right now.",
                              reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_name = query.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    try:
        if query.data.startswith('search_specific_'):
            movie_id = query.data.split('_')[2]
            # Get movie details from TMDB
            url = f"{TMDB_BASE_URL}/movie/{movie_id}"
            response = requests.get(url, params={"api_key": TMDB_API_KEY})
            movie = response.json()

            # Create a message with movie details
            movie_text = f"{movie['title']} ({movie.get('release_date', '')[:4]})"

            # Send a temporary message to user's private chat
            class SimulatedMessage:
                def __init__(self, chat_id, text, from_user):
                    self.chat_id = chat_id
                    self.text = text
                    self.from_user = from_user

                def reply_text(self, *args, **kwargs):
                    return query.message.reply_text(*args, **kwargs)

                def reply_photo(self, *args, **kwargs):
                    return query.message.reply_photo(*args, **kwargs)

            # Create a proper message object
            simulated_message = SimulatedMessage(
                chat_id=query.message.chat_id,
                text=movie['title'],
                from_user=query.from_user
            )

            # Create a proper update object
            class SimulatedUpdate:
                def __init__(self, message):
                    self.message = message

            simulated_update = SimulatedUpdate(simulated_message)

            # Perform the search
            await search_movie(simulated_update, context)
            return
        if query.data == 'genre_horror':
            await get_genre_movies(query.message, context, GENRE_IDS['horror'], "Horror")
        elif query.data == 'genre_romance':
            await get_genre_movies(query.message, context, GENRE_IDS['romance'], "Romance")
        elif query.data == 'genre_crime':
            await get_genre_movies(query.message, context, GENRE_IDS['crime'], "Crime")
        elif query.data == 'random_movies':
            await get_random_movies_by_genre(query.message, context)
        if query.data == 'random_movies':
            await get_random_movies_by_genre(query.message, context)
        elif query.data == 'random_horror':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['horror'])
        elif query.data == 'random_crime':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['crime'])
        elif query.data == 'random_romance':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['romance'])
        elif query.data == 'horror_movies':
            await get_horror_movies(query.message, context)
        elif query.data == 'search_movies':
            USER_CONTEXT[query.message.chat_id] = 'movie'
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "🔍 Just type the name of any movie you want to search for!",
                reply_markup=reply_markup
            )
        elif query.data == 'search_actor':
            USER_CONTEXT[query.message.chat_id] = 'actor'
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "🎭 Just type the name of any actor to see their movies!",
                reply_markup=reply_markup
            )
        elif query.data == 'help':
            help_text = ("📖 How to use this bot:\n\n"
                        "1. Simply type any movie name\n"
                        "2. Or type any actor name to find their movies\n"
                        "3. I'll show you the details\n"
                        "4. Check out popular movies in both Hollywood and Bollywood\n"
                        "5. Try our random movie suggestions by genre!\n"
                        "Need more help? Just type /start to see the main menu again! or msg @balaram129")
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                help_text,
                reply_markup=reply_markup
            )
        elif query.data == 'popular':
            await get_popular_movies(query.message, context)
        elif query.data == 'bollywood_popular':
            await get_bollywood_popular_movies(query.message, context)
        elif query.data == 'start_menu':
            keyboard = [
                [InlineKeyboardButton("🔍 Download movies", callback_data='search_movies'),
                 InlineKeyboardButton("👻 Horror Movies", callback_data='horror_movies')],
                [
                    InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
                    InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
                    InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
                ],
                [InlineKeyboardButton("📈 Popular Movies", callback_data='popular')],
                [InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
                [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
                [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
                [InlineKeyboardButton("❓ Help", callback_data='help')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "👋 Welcome to moviieshubb_bot!\n\nClick on /start to restart or type",
                reply_markup=reply_markup
            )

    except Exception as e:
        print(f"Error in button callback: {e}")
        keyboard = [
            [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(
            query.message,
            context,
            "Sorry, there was an error processing your request. Please try again.",
            reply_markup=reply_markup
        )

async def handle_user_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_context = USER_CONTEXT.get(update.message.chat_id, "movie")
    if user_context == "actor":
        await search_by_actor(update, context)
    else:
        await search_movie(update, context)

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_message_later(context, update.message.chat_id, update.message.message_id)
    await handle_user_query(update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Exception while handling an update: {context.error}")
    if isinstance(context.error, Conflict):
        print("Bot instance already running. Exiting...")
        sys.exit(1)
    elif isinstance(context.error, NetworkError):
        print("Network error occurred. Waiting before retry...")
        await asyncio.sleep(1)
    else:
        print(f"Unexpected error: {context.error}")


def main():
    try:
        application = (
            Application.builder()
            .token(TELEGRAM_TOKEN)
            .build()
        )

        # Add existing handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CallbackQueryHandler(button_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))
        application.add_handler(CommandHandler("viewsearches", view_searches_command))

        # Add error handler
        application.add_error_handler(error_handler)

        # Set up the cleanup job to run every 10 seconds
        job_queue = application.job_queue
        job_queue.run_repeating(cleanup_job, interval=10, first=0)

        # Add the inactive user check job (runs every 6 hours)
        job_queue.run_repeating(check_inactive_users, interval=21600, first=21600)

        # Update stastics more frequently (every 5 minutes)
        job_queue.run_repeating(update_stastics_job, interval=300, first=0)

        # Initial statistics update
        print("Performing initial statistics update...")
        stats = SearchStatistics()
        stats.update_stastics_file()
        print("Initial statistics update completed")

        # Start the bot
        print("Starting bot...")
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

    except Exception as e:
        print(f"Error starting bot: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

# Test the logger
logger = SearchLogger()
logger.log_search(123456, "TestUser", "movie", "Avatar")

# Check recent searches
recent = logger.get_recent_searches()
print("Recent searches:", recent)import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import Conflict, NetworkError, TelegramError
import nest_asyncio
import sys
import random
from typing import Optional, Dict
from datetime import datetime, timedelta
import pickle
from special_cases_managerss import SpecialCasesManager
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import json
from datetime import datetime
from pathlib import Path


class SearchLogger:
    def __init__(self, log_file="search_logs.json"):
        self.log_file = log_file
        self.ensure_log_file_exists()

    def ensure_log_file_exists(self):
        # Create the file with an empty list if it doesn't exist or is empty
        if not Path(self.log_file).exists() or Path(self.log_file).stat().st_size == 0:
            with open(self.log_file, 'w') as f:
                json.dump([], f)

    def log_search(self, user_id: int, user_name: str, search_type: str, search_query: str):
        try:
            # First ensure the file exists and has valid JSON
            self.ensure_log_file_exists()

            # Read existing logs
            try:
                with open(self.log_file, 'r') as f:
                    logs = json.load(f)
            except json.JSONDecodeError:
                # If there's an error reading the JSON, start with an empty list
                logs = []

            # Create new log entry
            log_entry = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "user_id": user_id,
                "user_name": user_name,
                "search_type": search_type,
                "search_query": search_query
            }

            # Add new entry
            logs.append(log_entry)

            # Write back to file
            with open(self.log_file, 'w') as f:
                json.dump(logs, f, indent=2)

        except Exception as e:
            print(f"Error logging search: {e}")

    def get_recent_searches(self, limit: int = 100):
        try:
            # First ensure the file exists and has valid JSON
            self.ensure_log_file_exists()

            with open(self.log_file, 'r') as f:
                try:
                    logs = json.load(f)
                except json.JSONDecodeError:
                    return []
            return logs[-limit:]
        except Exception as e:
            print(f"Error getting recent searches: {e}")
            return []


# Create an instance of the logger
search_logger = SearchLogger()


# After your other global variables
special_cases_manager = SpecialCasesManager()

# Initialize some cases if you want (optional)
special_cases_manager.add_case(
    "pushpa 2",
    ["pushpa2", "pushpa-2", "pushpa2therule", "pushpa 2 the rule"],
    [
        {"url": "https://example4.com", "language": "Hindi"},
        {"url": "https://example5.com", "language": "Telugu"}
    ]
)

special_cases_manager.add_case(
    "venom",
    ["venom", "venom1", "venom2"],
    [
        {"url": "https://www.udlinks.com/3I1l", "language": "hindi"}
    ]
)




nest_asyncio.apply()

TELEGRAM_TOKEN = "7883754025:AAHUDU-_EM4QYome14k_28PQbPTWsl_9w6s"
TMDB_API_KEY = "c3b8704a4df65146c194940351efa9a2"
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
DELETE_TIMEOUT = 420  # 7 minutes in seconds
DISCLAIMER = "⚠️ This message will be deleted in 7 minutes"
HORROR_GENRE_ID = 27  # TMDB's genre ID for horror movies



USER_CONTEXT = {}

GENRE_IDS = {
    'horror': 27,
    'crime': 80,
    'romance': 10749
}


class TMDBAPIHandler:
    def __init__(self, api_key, base_url="https://api.themoviedb.org/3"):
        self.api_key = api_key
        self.base_url = base_url
        self.session = self._create_session()

    def _create_session(self):
        session = requests.Session()

        # Configure retry strategy
        retries = Retry(
            total=5,  # Total number of retries
            backoff_factor=0.5,  # Wait 0.5, 1, 2, 4, 8 seconds between retries
            status_forcelist=[500, 502, 503, 504, 408, 429]  # HTTP status codes to retry on
        )

        # Add retry adapter to session
        adapter = HTTPAdapter(max_retries=retries)
        session.mount('http://', adapter)
        session.mount('https://', adapter)

        return session

    def make_request(self, endpoint, params=None):
        if params is None:
            params = {}

        # Always include API key
        params['api_key'] = self.api_key

        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                response = self.session.get(
                    f"{self.base_url}{endpoint}",
                    params=params,
                    timeout=10  # 10 seconds timeout
                )
                response.raise_for_status()
                return response.json()

            except requests.exceptions.ConnectionError as e:
                if attempt == max_attempts - 1:
                    raise Exception("Unable to connect to TMDB API. Please check your internet connection.") from e
                time.sleep(2 ** attempt)  # Exponential backoff

            except requests.exceptions.Timeout as e:
                if attempt == max_attempts - 1:
                    raise Exception("TMDB API request timed out. Please try again later.") from e
                time.sleep(2 ** attempt)

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:  # Rate limit exceeded
                    retry_after = int(e.response.headers.get('Retry-After', 5))
                    time.sleep(retry_after)
                    continue
                raise Exception(f"TMDB API error: {e.response.status_code}") from e


LAST_ACTIVITY_FILE = "user_activity.pkl"
INACTIVITY_THRESHOLD = timedelta(hours=78)


class SearchStatistics:
    def __init__(self, log_file="search_logs.json", stats_file="stastics.txt"):
        self.log_file = log_file
        self.stats_file = stats_file
        self.search_logger = SearchLogger(log_file)
        # Ensure stastics file exists
        self.update_stastics_file()
        print(f"SearchStatistics initialized. Stats file: {stats_file}")

    def _load_searches(self):
        """Load searches from the log file"""
        try:
            with open(self.log_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def get_most_searched(self, days=None):
        """Get most searched queries within specified days"""
        searches = self._load_searches()
        if not searches:
            return []

        # Filter by date if days is specified
        if days:
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            searches = [s for s in searches if s['timestamp'][:10] >= cutoff_date]

        # Count search queries
        query_counts = {}
        for search in searches:
            query = search['search_query'].lower()
            query_counts[query] = query_counts.get(query, 0) + 1

        # Sort by count and return top 10
        return sorted(query_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    def get_user_search_history(self, limit=50):
        """Get recent user search history"""
        searches = self._load_searches()
        return searches[-limit:] if searches else []

    def update_stastics_file(self):  # Changed method name to match file name
        try:
            print(f"Updating stastics file at {datetime.now()}")

            # Check if log file exists and has data
            if not Path(self.log_file).exists():
                print(f"Log file {self.log_file} does not exist!")
                return

            # Load searches
            searches = self._load_searches()
            if not searches:
                print("No search data found in logs")
                stats_text = "No search data available yet.\nLast Updated: " + datetime.now().strftime(
                    '%Y-%m-%d %H:%M:%S')
            else:
                # Get statistics for different time periods
                all_time = self.get_most_searched()
                today = self.get_most_searched(days=1)
                week = self.get_most_searched(days=7)
                year = self.get_most_searched(days=365)
                user_history = self.get_user_search_history(limit=50)

                stats_text = self._format_stastics(all_time, today, week, year, user_history)  # Changed method name

            # Write to stastics file
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                f.write(stats_text)

            print(f"Stastics file updated successfully at {datetime.now()}")

            # Debug: Read and print file contents
            with open(self.stats_file, 'r', encoding='utf-8') as f:
                content = f.read()
            print(f"Stastics file size: {len(content)} bytes")

        except Exception as e:
            print(f"Error updating stastics file: {e}")
            import traceback
            traceback.print_exc()

    def _format_stastics(self, all_time, today, week, year, user_history):  # Changed method name
        stats_text = "Movie Search Stastics\n"  # Changed heading
        stats_text += "=" * 50 + "\n\n"

        # Add section for each time period
        sections = [
            ("All-Time Most Searched Movies:", all_time),
            ("Today's Most Searched Movies:", today),
            ("This Week's Most Searched Movies:", week),
            ("This Year's Most Searched Movies:", year)
        ]

        for title, data in sections:
            stats_text += f"{title}\n"
            if data:
                stats_text += "\n".join(f"{i + 1}. {movie} ({count} searches)"
                                      for i, (movie, count) in enumerate(data))
            else:
                stats_text += "No searches in this period"
            stats_text += "\n\n"

        # Add user history section
        stats_text += "Recent User Search History:\n"
        stats_text += "=" * 50 + "\n"
        if user_history:
            for search in user_history:
                stats_text += f"\nTime: {search['timestamp']}\n"
                stats_text += f"User: {search['user_name']} (ID: {search['user_id']})\n"
                stats_text += f"Search Type: {search['search_type']}\n"
                stats_text += f"Query: {search['search_query']}\n"
                stats_text += "-" * 30 + "\n"
        else:
            stats_text += "\nNo user search history available yet\n"

        stats_text += f"\nLast Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        return stats_text

# Modify the update_statistics_job to include error handling and logging
async def update_stastics_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        print(f"Starting stastics update job at {datetime.now()}")
        stats = SearchStatistics()
        stats.update_stastics_file()
        print(f"Completed stastics update job at {datetime.now()}")
    except Exception as e:
        print(f"Error in stastics update job: {e}")
        import traceback
        traceback.print_exc()

async def view_searches_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only allow yourself to see the searches
    if update.message.from_user.id == 6822829183:  # Replace with your Telegram ID
        recent_searches = search_logger.get_recent_searches(limit=10)  # Get last 10 searches

        message = "Recent Searches:\n\n"
        for search in recent_searches:
            message += f"👤 User: {search['user_name']}\n"
            message += f"🔍 Query: {search['search_query']}\n"
            message += f"⏰ Time: {search['timestamp']}\n"
            message += f"Type: {search['search_type']}\n\n"

        await update.message.reply_text(message)
    else:
        await update.message.reply_text("You don't have permission to use this command.")


# Add this to your command handlers

class UserActivityManager:
    def __init__(self):
        self.user_activity = {}
        self.load_activity()

    def load_activity(self):
        if Path(LAST_ACTIVITY_FILE).exists():
            try:
                with open(LAST_ACTIVITY_FILE, 'rb') as f:
                    self.user_activity = pickle.load(f)
            except Exception as e:
                print(f"Error loading user activity: {e}")
                self.user_activity = {}

    def save_activity(self):
        try:
            with open(LAST_ACTIVITY_FILE, 'wb') as f:
                pickle.dump(self.user_activity, f)
        except Exception as e:
            print(f"Error saving user activity: {e}")

    def update_user_activity(self, user_id: int, user_name: str):
        self.user_activity[user_id] = {
            'last_active': datetime.now(),
            'name': user_name
        }
        self.save_activity()

    def get_inactive_users(self):
        current_time = datetime.now()
        inactive_users = []

        for user_id, data in self.user_activity.items():
            if (current_time - data['last_active']) >= INACTIVITY_THRESHOLD:
                inactive_users.append({
                    'user_id': user_id,
                    'name': data['name'],
                    'last_active': data['last_active']
                })

        return inactive_users


# Create global instance
activity_manager = UserActivityManager()


# Modify the handle_user_message function to track activity
async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    await delete_message_later(context, update.message.chat_id, update.message.message_id)
    await handle_user_query(update, context)


# Add a new function to check for inactive users
async def check_inactive_users(context: ContextTypes.DEFAULT_TYPE):
    inactive_users = activity_manager.get_inactive_users()

    for user in inactive_users:
        try:
            message = f"Hey {user['name']} 👋,\n\nI am missing you dear! 💫\nIt's been a while since we last chatted. Come back and discover some amazing movies! 🎬"

            await context.bot.send_message(
                chat_id=user['user_id'],
                text=message,
                parse_mode='Markdown'
            )

            # Update the last activity to prevent spam
            activity_manager.update_user_activity(user['user_id'], user['name'])

        except Exception as e:
            print(f"Error sending reminder to user {user['user_id']}: {e}")

class MessageTracker:
    def __init__(self):
        self.messages: Dict[int, Dict[int, datetime]] = {}

    async def add_message(self, chat_id: int, message_id: int):
        if chat_id not in self.messages:
            self.messages[chat_id] = {}
        self.messages[chat_id][message_id] = datetime.now() + timedelta(seconds=DELETE_TIMEOUT)

    async def cleanup_messages(self, context: ContextTypes.DEFAULT_TYPE):
        current_time = datetime.now()
        for chat_id in list(self.messages.keys()):
            for message_id, expiry_time in list(self.messages[chat_id].items()):
                if current_time >= expiry_time:
                    try:
                        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                    except TelegramError:
                        pass  # Message might already be deleted
                    finally:
                        del self.messages[chat_id][message_id]
            if not self.messages[chat_id]:
                del self.messages[chat_id]

message_tracker = MessageTracker()

async def cleanup_job(context: ContextTypes.DEFAULT_TYPE):
    await message_tracker.cleanup_messages(context)

async def delete_message_later(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int):
    await message_tracker.add_message(chat_id, message_id)

async def send_with_warning(message, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None, parse_mode=None):
    try:
        if hasattr(message, 'reply_text'):
            sent_message = await message.reply_text(
                f"{text}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await message.edit_text(
                f"{text}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

        await delete_message_later(context, sent_message.chat_id, sent_message.message_id)
        return sent_message
    except TelegramError as e:
        print(f"Error sending message: {e}")
        return None

async def send_photo_with_warning(message, context: ContextTypes.DEFAULT_TYPE, photo: str, caption: str, reply_markup=None, parse_mode=None):
    try:
        if hasattr(message, 'reply_photo'):
            sent_message = await message.reply_photo(
                photo=photo,
                caption=f"{caption}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await context.bot.send_photo(
                chat_id=message.chat_id,
                photo=photo,
                caption=f"{caption}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

        await delete_message_later(context, sent_message.chat_id, sent_message.message_id)
        return sent_message
    except TelegramError as e:
        print(f"Error sending photo: {e}")
        return None


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    keyboard = [
        [InlineKeyboardButton("  DOWNLOAD MOVIES", callback_data='search_movies')],
        [
            InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
            InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
            InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
        ],
        [InlineKeyboardButton("📈 Popular Movies", callback_data='popular'),
         InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
        [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
        [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_with_warning(
        update.message,
        context,
        f"👋 Hello {user_name}! Welcome to @movieshuba11_bot!\n\nClick on /start to restart or type",
        reply_markup=reply_markup
    )

async def show_start_menu(message, context: ContextTypes.DEFAULT_TYPE):
    # Get user's name from the callback query
    user_name = message._effective_user.first_name if hasattr(message, '_effective_user') else "there"
    keyboard = [
        [InlineKeyboardButton(" Download movies", callback_data='search_movies')],
        [
            InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
            InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
            InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
        ],
        [InlineKeyboardButton("📈 Popular Movies", callback_data='popular')],
        [InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
        [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
        [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_with_warning(
        message,
        context,
        f"👋 Hello {user_name}! Welcome to moviieshubb_bot!\n\nClick on /start to restart or type",
        reply_markup=reply_markup
    )



async def get_random_movies_by_genre(message, context: ContextTypes.DEFAULT_TYPE, genre_id=None):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "sort_by": "popularity.desc",
            "page": 1
        }

        if genre_id:
            params["with_genres"] = genre_id

        response = requests.get(url, params=params)
        response.raise_for_status()
        total_pages = min(response.json().get("total_pages", 1), 500)

        random_page = random.randint(1, total_pages)
        params["page"] = random_page

        response = requests.get(url, params=params)
        response.raise_for_status()

        all_movies = response.json().get("results", [])
        random_movies = random.sample(all_movies, min(5, len(all_movies)))

        response_text = "🎲 Random Movie Suggestions:\n\n"
        keyboard = []
        for i, movie in enumerate(random_movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"
            keyboard.append([InlineKeyboardButton(f"🔍 Search {movie['title']}", callback_data=f'search_specific_{movie["id"]}')])

        keyboard.extend([
            [
                InlineKeyboardButton("👻 Horror", callback_data='random_horror'),
                InlineKeyboardButton("🔪 Crime", callback_data='random_crime'),
                InlineKeyboardButton("💝 Romance", callback_data='random_romance')
            ],
            [InlineKeyboardButton("🎲 More Random", callback_data='random_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching random movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='random_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                                "Sorry, couldn't fetch random movies right now.",
                                reply_markup=reply_markup)


async def get_popular_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/movie/popular"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "🎬 Currently Popular Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching popular movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='popular')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch popular movies right now.",
                              reply_markup=reply_markup)

async def get_horror_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "with_genres": HORROR_GENRE_ID,
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "👻 Popular Horror Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton("👻 More Horror Movies", callback_data='horror_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching horror movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='horror_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch horror movies right now.",
                              reply_markup=reply_markup)

async def get_bollywood_popular_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "region": "IN",
            "with_original_language": "hi",
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "🎬  Bollywood Popular Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching Bollywood movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='bollywood_popular')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch Bollywood movies right now.",
                              reply_markup=reply_markup)


async def search_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    special_case, special_links = special_cases_manager.is_special_case(query)
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Log the search
    search_logger.log_search(user_id, user_name, "movie", query)
    try:
        tmdb_handler = TMDBAPIHandler(TMDB_API_KEY)

        # Search for movie
        results = tmdb_handler.make_request(
            "/search/movie",
            params={"query": query, "language": "en-US"}
        ).get("results", [])

        if results:
            movie = results[0]
            movie_id = movie["id"]

            # Get movie details
            movie_details = tmdb_handler.make_request(f"/movie/{movie_id}")
            providers = tmdb_handler.make_request(f"/movie/{movie_id}/watch/providers").get("results", {}).get("US",
                                                                                                               {}).get(
                "flatrate", [])

        search_url = f"{TMDB_BASE_URL}/search/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        if results:
            movie = results[0]
            movie_id = movie["id"]

            details_url = f"{TMDB_BASE_URL}/movie/{movie_id}"
            watch_providers_url = f"{TMDB_BASE_URL}/movie/{movie_id}/watch/providers"

            details_response = requests.get(details_url, params={"api_key": TMDB_API_KEY})
            providers_response = requests.get(watch_providers_url, params={"api_key": TMDB_API_KEY})

            movie_details = details_response.json()
            providers = providers_response.json().get("results", {}).get("US", {}).get("flatrate", [])

            keyboard = [
                [InlineKeyboardButton(" Search Another Movie", callback_data='search_movies')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            response_text = (
                f"*{movie_details['title']}* ({movie_details.get('release_date', '')[:4]})\n\n"
                f"Plot: {movie_details.get('overview', 'No plot available')}\n\n"
            )

            if providers:
                response_text += "Available on: " + ", ".join(p["provider_name"] for p in providers) + "\n\n"
            else:
                response_text += "Streaming information not available\n\n"

            if special_case and special_links:
                response_text += "Download Links:\n"
                for link in special_links:
                    lang_text = f" ({link['language']})" if link.get('language') else ""
                    response_text += f"• {link['url']}{lang_text}\n"
            else:
                response_text += "download link comming soon msg @balaram129"

            if movie_details.get("poster_path"):
                poster_url = f"{TMDB_IMAGE_BASE_URL}{movie_details['poster_path']}"
                await send_photo_with_warning(update.message, context, photo=poster_url, caption=response_text, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                await send_with_warning(update.message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            keyboard = [
                [InlineKeyboardButton(" Try Again", callback_data='search_movies')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(update.message, context, "No movies found matching your search.", reply_markup=reply_markup)
    except Exception as e:
        print(f"Error in movie search: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(update.message, context,
                              "Sorry, there was an error processing your request. Please try again.",
                              reply_markup=reply_markup)

async def search_by_actor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Log the search
    search_logger.log_search(user_id, user_name, "actor", query)
    try:
        search_url = f"{TMDB_BASE_URL}/search/person"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        if results:
            actor = results[0]
            actor_id = actor["id"]

            actor_details_url = f"{TMDB_BASE_URL}/person/{actor_id}"
            movies_url = f"{TMDB_BASE_URL}/person/{actor_id}/movie_credits"

            actor_details_response = requests.get(actor_details_url, params={"api_key": TMDB_API_KEY})
            movies_response = requests.get(movies_url, params={"api_key": TMDB_API_KEY})

            actor_details = actor_details_response.json()
            movies = movies_response.json().get("cast", [])

            movies_with_rating = [m for m in movies if m.get("vote_average", 0) > 0]
            sorted_movies = sorted(movies_with_rating, key=lambda x: x.get("vote_average", 0), reverse=True)

            popular_movies = [m for m in sorted_movies if m.get("vote_average", 0) >= 7][:4]
            unpopular_movies = [m for m in sorted_movies if m.get("vote_average", 0) < 7][:4]

            response_text = f"🎭 {actor['name']}\n"
            if actor_details.get("birthday"):
                response_text += f"Birthday: {actor_details['birthday']}\n"
            if actor_details.get("place_of_birth"):
                response_text += f"Birthplace: {actor_details['place_of_birth']}\n"

            response_text += "\n📈 Highly Rated Movies:\n"
            for i, movie in enumerate(popular_movies, 1):
                response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
                response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"

            response_text += "\n📉 Other Notable Movies:\n"
            for i, movie in enumerate(unpopular_movies, 1):
                response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
                response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"

            keyboard = [
                [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
                [InlineKeyboardButton(" Search Another Actor", callback_data='search_actor')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            if actor.get("profile_path"):
                actor_image_url = f"{TMDB_IMAGE_BASE_URL}{actor['profile_path']}"
                await send_photo_with_warning(
                    update.message,
                    context,
                    photo=actor_image_url,
                    caption=response_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await send_with_warning(
                    update.message,
                    context,
                    response_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
        else:
            keyboard = [
                [InlineKeyboardButton(" Try Again", callback_data='search_actor')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                update.message,
                context,
                "No actor found matching your search.",
                reply_markup=reply_markup
            )
    except Exception as e:
        print(f"Error in actor search: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='search_actor')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(
            update.message,
            context,
            "Sorry, there was an error processing your request. Please try again.",
            reply_markup=reply_markup
        )
def is_special_case(query):
    query_lower = query.lower().strip()
    for key, case in special_cases_manager.items():
        if query_lower == key.lower() or query_lower in [v.lower() for v in case["variants"]]:
            return True, case["links"]
    return False, []

async def get_genre_movies(message, context: ContextTypes.DEFAULT_TYPE, genre_id: int, genre_name: str):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "with_genres": genre_id,
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = f"🎬 Popular {genre_name} Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching {genre_name} movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data=f'genre_{genre_name.lower()}')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              f"Sorry, couldn't fetch {genre_name} movies right now.",
                              reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_name = query.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    try:
        if query.data.startswith('search_specific_'):
            movie_id = query.data.split('_')[2]
            # Get movie details from TMDB
            url = f"{TMDB_BASE_URL}/movie/{movie_id}"
            response = requests.get(url, params={"api_key": TMDB_API_KEY})
            movie = response.json()

            # Create a message with movie details
            movie_text = f"{movie['title']} ({movie.get('release_date', '')[:4]})"

            # Send a temporary message to user's private chat
            class SimulatedMessage:
                def __init__(self, chat_id, text, from_user):
                    self.chat_id = chat_id
                    self.text = text
                    self.from_user = from_user

                def reply_text(self, *args, **kwargs):
                    return query.message.reply_text(*args, **kwargs)

                def reply_photo(self, *args, **kwargs):
                    return query.message.reply_photo(*args, **kwargs)

            # Create a proper message object
            simulated_message = SimulatedMessage(
                chat_id=query.message.chat_id,
                text=movie['title'],
                from_user=query.from_user
            )

            # Create a proper update object
            class SimulatedUpdate:
                def __init__(self, message):
                    self.message = message

            simulated_update = SimulatedUpdate(simulated_message)

            # Perform the search
            await search_movie(simulated_update, context)
            return
        if query.data == 'genre_horror':
            await get_genre_movies(query.message, context, GENRE_IDS['horror'], "Horror")
        elif query.data == 'genre_romance':
            await get_genre_movies(query.message, context, GENRE_IDS['romance'], "Romance")
        elif query.data == 'genre_crime':
            await get_genre_movies(query.message, context, GENRE_IDS['crime'], "Crime")
        elif query.data == 'random_movies':
            await get_random_movies_by_genre(query.message, context)
        if query.data == 'random_movies':
            await get_random_movies_by_genre(query.message, context)
        elif query.data == 'random_horror':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['horror'])
        elif query.data == 'random_crime':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['crime'])
        elif query.data == 'random_romance':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['romance'])
        elif query.data == 'horror_movies':
            await get_horror_movies(query.message, context)
        elif query.data == 'search_movies':
            USER_CONTEXT[query.message.chat_id] = 'movie'
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "🔍 Just type the name of any movie you want to search for!",
                reply_markup=reply_markup
            )
        elif query.data == 'search_actor':
            USER_CONTEXT[query.message.chat_id] = 'actor'
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "🎭 Just type the name of any actor to see their movies!",
                reply_markup=reply_markup
            )
        elif query.data == 'help':
            help_text = ("📖 How to use this bot:\n\n"
                        "1. Simply type any movie name\n"
                        "2. Or type any actor name to find their movies\n"
                        "3. I'll show you the details\n"
                        "4. Check out popular movies in both Hollywood and Bollywood\n"
                        "5. Try our random movie suggestions by genre!\n"
                        "Need more help? Just type /start to see the main menu again! or msg @balaram129")
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                help_text,
                reply_markup=reply_markup
            )
        elif query.data == 'popular':
            await get_popular_movies(query.message, context)
        elif query.data == 'bollywood_popular':
            await get_bollywood_popular_movies(query.message, context)
        elif query.data == 'start_menu':
            keyboard = [
                [InlineKeyboardButton("🔍 Download movies", callback_data='search_movies'),
                 InlineKeyboardButton("👻 Horror Movies", callback_data='horror_movies')],
                [
                    InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
                    InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
                    InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
                ],
                [InlineKeyboardButton("📈 Popular Movies", callback_data='popular')],
                [InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
                [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
                [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
                [InlineKeyboardButton("❓ Help", callback_data='help')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "👋 Welcome to moviieshubb_bot!\n\nClick on /start to restart or type",
                reply_markup=reply_markup
            )

    except Exception as e:
        print(f"Error in button callback: {e}")
        keyboard = [
            [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(
            query.message,
            context,
            "Sorry, there was an error processing your request. Please try again.",
            reply_markup=reply_markup
        )

async def handle_user_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_context = USER_CONTEXT.get(update.message.chat_id, "movie")
    if user_context == "actor":
        await search_by_actor(update, context)
    else:
        await search_movie(update, context)

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_message_later(context, update.message.chat_id, update.message.message_id)
    await handle_user_query(update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Exception while handling an update: {context.error}")
    if isinstance(context.error, Conflict):
        print("Bot instance already running. Exiting...")
        sys.exit(1)
    elif isinstance(context.error, NetworkError):
        print("Network error occurred. Waiting before retry...")
        await asyncio.sleep(1)
    else:
        print(f"Unexpected error: {context.error}")


def main():
    try:
        application = (
            Application.builder()
            .token(TELEGRAM_TOKEN)
            .build()
        )

        # Add existing handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CallbackQueryHandler(button_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))
        application.add_handler(CommandHandler("viewsearches", view_searches_command))

        # Add error handler
        application.add_error_handler(error_handler)

        # Set up the cleanup job to run every 10 seconds
        job_queue = application.job_queue
        job_queue.run_repeating(cleanup_job, interval=10, first=0)

        # Add the inactive user check job (runs every 6 hours)
        job_queue.run_repeating(check_inactive_users, interval=21600, first=21600)

        # Update stastics more frequently (every 5 minutes)
        job_queue.run_repeating(update_stastics_job, interval=300, first=0)

        # Initial statistics update
        print("Performing initial statistics update...")
        stats = SearchStatistics()
        stats.update_stastics_file()
        print("Initial statistics update completed")

        # Start the bot
        print("Starting bot...")
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

    except Exception as e:
        print(f"Error starting bot: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

# Test the logger
logger = SearchLogger()
logger.log_search(123456, "TestUser", "movie", "Avatar")

# Check recent searches
recent = logger.get_recent_searches()
print("Recent searches:", recent)import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import Conflict, NetworkError, TelegramError
import nest_asyncio
import sys
import random
from typing import Optional, Dict
from datetime import datetime, timedelta
import pickle
from special_cases_managerss import SpecialCasesManager
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import json
from datetime import datetime
from pathlib import Path


class SearchLogger:
    def __init__(self, log_file="search_logs.json"):
        self.log_file = log_file
        self.ensure_log_file_exists()

    def ensure_log_file_exists(self):
        # Create the file with an empty list if it doesn't exist or is empty
        if not Path(self.log_file).exists() or Path(self.log_file).stat().st_size == 0:
            with open(self.log_file, 'w') as f:
                json.dump([], f)

    def log_search(self, user_id: int, user_name: str, search_type: str, search_query: str):
        try:
            # First ensure the file exists and has valid JSON
            self.ensure_log_file_exists()

            # Read existing logs
            try:
                with open(self.log_file, 'r') as f:
                    logs = json.load(f)
            except json.JSONDecodeError:
                # If there's an error reading the JSON, start with an empty list
                logs = []

            # Create new log entry
            log_entry = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "user_id": user_id,
                "user_name": user_name,
                "search_type": search_type,
                "search_query": search_query
            }

            # Add new entry
            logs.append(log_entry)

            # Write back to file
            with open(self.log_file, 'w') as f:
                json.dump(logs, f, indent=2)

        except Exception as e:
            print(f"Error logging search: {e}")

    def get_recent_searches(self, limit: int = 100):
        try:
            # First ensure the file exists and has valid JSON
            self.ensure_log_file_exists()

            with open(self.log_file, 'r') as f:
                try:
                    logs = json.load(f)
                except json.JSONDecodeError:
                    return []
            return logs[-limit:]
        except Exception as e:
            print(f"Error getting recent searches: {e}")
            return []


# Create an instance of the logger
search_logger = SearchLogger()


# After your other global variables
special_cases_manager = SpecialCasesManager()

# Initialize some cases if you want (optional)
special_cases_manager.add_case(
    "pushpa 2",
    ["pushpa2", "pushpa-2", "pushpa2therule", "pushpa 2 the rule"],
    [
        {"url": "https://example4.com", "language": "Hindi"},
        {"url": "https://example5.com", "language": "Telugu"}
    ]
)

special_cases_manager.add_case(
    "venom",
    ["venom", "venom1", "venom2"],
    [
        {"url": "https://www.udlinks.com/3I1l", "language": "hindi"}
    ]
)




nest_asyncio.apply()

TELEGRAM_TOKEN = "7883754025:AAHUDU-_EM4QYome14k_28PQbPTWsl_9w6s"
TMDB_API_KEY = "c3b8704a4df65146c194940351efa9a2"
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
DELETE_TIMEOUT = 420  # 7 minutes in seconds
DISCLAIMER = "⚠️ This message will be deleted in 7 minutes"
HORROR_GENRE_ID = 27  # TMDB's genre ID for horror movies



USER_CONTEXT = {}

GENRE_IDS = {
    'horror': 27,
    'crime': 80,
    'romance': 10749
}


class TMDBAPIHandler:
    def __init__(self, api_key, base_url="https://api.themoviedb.org/3"):
        self.api_key = api_key
        self.base_url = base_url
        self.session = self._create_session()

    def _create_session(self):
        session = requests.Session()

        # Configure retry strategy
        retries = Retry(
            total=5,  # Total number of retries
            backoff_factor=0.5,  # Wait 0.5, 1, 2, 4, 8 seconds between retries
            status_forcelist=[500, 502, 503, 504, 408, 429]  # HTTP status codes to retry on
        )

        # Add retry adapter to session
        adapter = HTTPAdapter(max_retries=retries)
        session.mount('http://', adapter)
        session.mount('https://', adapter)

        return session

    def make_request(self, endpoint, params=None):
        if params is None:
            params = {}

        # Always include API key
        params['api_key'] = self.api_key

        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                response = self.session.get(
                    f"{self.base_url}{endpoint}",
                    params=params,
                    timeout=10  # 10 seconds timeout
                )
                response.raise_for_status()
                return response.json()

            except requests.exceptions.ConnectionError as e:
                if attempt == max_attempts - 1:
                    raise Exception("Unable to connect to TMDB API. Please check your internet connection.") from e
                time.sleep(2 ** attempt)  # Exponential backoff

            except requests.exceptions.Timeout as e:
                if attempt == max_attempts - 1:
                    raise Exception("TMDB API request timed out. Please try again later.") from e
                time.sleep(2 ** attempt)

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:  # Rate limit exceeded
                    retry_after = int(e.response.headers.get('Retry-After', 5))
                    time.sleep(retry_after)
                    continue
                raise Exception(f"TMDB API error: {e.response.status_code}") from e


LAST_ACTIVITY_FILE = "user_activity.pkl"
INACTIVITY_THRESHOLD = timedelta(hours=78)


class SearchStatistics:
    def __init__(self, log_file="search_logs.json", stats_file="stastics.txt"):
        self.log_file = log_file
        self.stats_file = stats_file
        self.search_logger = SearchLogger(log_file)
        # Ensure stastics file exists
        self.update_stastics_file()
        print(f"SearchStatistics initialized. Stats file: {stats_file}")

    def _load_searches(self):
        """Load searches from the log file"""
        try:
            with open(self.log_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def get_most_searched(self, days=None):
        """Get most searched queries within specified days"""
        searches = self._load_searches()
        if not searches:
            return []

        # Filter by date if days is specified
        if days:
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            searches = [s for s in searches if s['timestamp'][:10] >= cutoff_date]

        # Count search queries
        query_counts = {}
        for search in searches:
            query = search['search_query'].lower()
            query_counts[query] = query_counts.get(query, 0) + 1

        # Sort by count and return top 10
        return sorted(query_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    def get_user_search_history(self, limit=50):
        """Get recent user search history"""
        searches = self._load_searches()
        return searches[-limit:] if searches else []

    def update_stastics_file(self):  # Changed method name to match file name
        try:
            print(f"Updating stastics file at {datetime.now()}")

            # Check if log file exists and has data
            if not Path(self.log_file).exists():
                print(f"Log file {self.log_file} does not exist!")
                return

            # Load searches
            searches = self._load_searches()
            if not searches:
                print("No search data found in logs")
                stats_text = "No search data available yet.\nLast Updated: " + datetime.now().strftime(
                    '%Y-%m-%d %H:%M:%S')
            else:
                # Get statistics for different time periods
                all_time = self.get_most_searched()
                today = self.get_most_searched(days=1)
                week = self.get_most_searched(days=7)
                year = self.get_most_searched(days=365)
                user_history = self.get_user_search_history(limit=50)

                stats_text = self._format_stastics(all_time, today, week, year, user_history)  # Changed method name

            # Write to stastics file
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                f.write(stats_text)

            print(f"Stastics file updated successfully at {datetime.now()}")

            # Debug: Read and print file contents
            with open(self.stats_file, 'r', encoding='utf-8') as f:
                content = f.read()
            print(f"Stastics file size: {len(content)} bytes")

        except Exception as e:
            print(f"Error updating stastics file: {e}")
            import traceback
            traceback.print_exc()

    def _format_stastics(self, all_time, today, week, year, user_history):  # Changed method name
        stats_text = "Movie Search Stastics\n"  # Changed heading
        stats_text += "=" * 50 + "\n\n"

        # Add section for each time period
        sections = [
            ("All-Time Most Searched Movies:", all_time),
            ("Today's Most Searched Movies:", today),
            ("This Week's Most Searched Movies:", week),
            ("This Year's Most Searched Movies:", year)
        ]

        for title, data in sections:
            stats_text += f"{title}\n"
            if data:
                stats_text += "\n".join(f"{i + 1}. {movie} ({count} searches)"
                                      for i, (movie, count) in enumerate(data))
            else:
                stats_text += "No searches in this period"
            stats_text += "\n\n"

        # Add user history section
        stats_text += "Recent User Search History:\n"
        stats_text += "=" * 50 + "\n"
        if user_history:
            for search in user_history:
                stats_text += f"\nTime: {search['timestamp']}\n"
                stats_text += f"User: {search['user_name']} (ID: {search['user_id']})\n"
                stats_text += f"Search Type: {search['search_type']}\n"
                stats_text += f"Query: {search['search_query']}\n"
                stats_text += "-" * 30 + "\n"
        else:
            stats_text += "\nNo user search history available yet\n"

        stats_text += f"\nLast Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        return stats_text

# Modify the update_statistics_job to include error handling and logging
async def update_stastics_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        print(f"Starting stastics update job at {datetime.now()}")
        stats = SearchStatistics()
        stats.update_stastics_file()
        print(f"Completed stastics update job at {datetime.now()}")
    except Exception as e:
        print(f"Error in stastics update job: {e}")
        import traceback
        traceback.print_exc()

async def view_searches_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only allow yourself to see the searches
    if update.message.from_user.id == 6822829183:  # Replace with your Telegram ID
        recent_searches = search_logger.get_recent_searches(limit=10)  # Get last 10 searches

        message = "Recent Searches:\n\n"
        for search in recent_searches:
            message += f"👤 User: {search['user_name']}\n"
            message += f"🔍 Query: {search['search_query']}\n"
            message += f"⏰ Time: {search['timestamp']}\n"
            message += f"Type: {search['search_type']}\n\n"

        await update.message.reply_text(message)
    else:
        await update.message.reply_text("You don't have permission to use this command.")


# Add this to your command handlers

class UserActivityManager:
    def __init__(self):
        self.user_activity = {}
        self.load_activity()

    def load_activity(self):
        if Path(LAST_ACTIVITY_FILE).exists():
            try:
                with open(LAST_ACTIVITY_FILE, 'rb') as f:
                    self.user_activity = pickle.load(f)
            except Exception as e:
                print(f"Error loading user activity: {e}")
                self.user_activity = {}

    def save_activity(self):
        try:
            with open(LAST_ACTIVITY_FILE, 'wb') as f:
                pickle.dump(self.user_activity, f)
        except Exception as e:
            print(f"Error saving user activity: {e}")

    def update_user_activity(self, user_id: int, user_name: str):
        self.user_activity[user_id] = {
            'last_active': datetime.now(),
            'name': user_name
        }
        self.save_activity()

    def get_inactive_users(self):
        current_time = datetime.now()
        inactive_users = []

        for user_id, data in self.user_activity.items():
            if (current_time - data['last_active']) >= INACTIVITY_THRESHOLD:
                inactive_users.append({
                    'user_id': user_id,
                    'name': data['name'],
                    'last_active': data['last_active']
                })

        return inactive_users


# Create global instance
activity_manager = UserActivityManager()


# Modify the handle_user_message function to track activity
async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    await delete_message_later(context, update.message.chat_id, update.message.message_id)
    await handle_user_query(update, context)


# Add a new function to check for inactive users
async def check_inactive_users(context: ContextTypes.DEFAULT_TYPE):
    inactive_users = activity_manager.get_inactive_users()

    for user in inactive_users:
        try:
            message = f"Hey {user['name']} 👋,\n\nI am missing you dear! 💫\nIt's been a while since we last chatted. Come back and discover some amazing movies! 🎬"

            await context.bot.send_message(
                chat_id=user['user_id'],
                text=message,
                parse_mode='Markdown'
            )

            # Update the last activity to prevent spam
            activity_manager.update_user_activity(user['user_id'], user['name'])

        except Exception as e:
            print(f"Error sending reminder to user {user['user_id']}: {e}")

class MessageTracker:
    def __init__(self):
        self.messages: Dict[int, Dict[int, datetime]] = {}

    async def add_message(self, chat_id: int, message_id: int):
        if chat_id not in self.messages:
            self.messages[chat_id] = {}
        self.messages[chat_id][message_id] = datetime.now() + timedelta(seconds=DELETE_TIMEOUT)

    async def cleanup_messages(self, context: ContextTypes.DEFAULT_TYPE):
        current_time = datetime.now()
        for chat_id in list(self.messages.keys()):
            for message_id, expiry_time in list(self.messages[chat_id].items()):
                if current_time >= expiry_time:
                    try:
                        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                    except TelegramError:
                        pass  # Message might already be deleted
                    finally:
                        del self.messages[chat_id][message_id]
            if not self.messages[chat_id]:
                del self.messages[chat_id]

message_tracker = MessageTracker()

async def cleanup_job(context: ContextTypes.DEFAULT_TYPE):
    await message_tracker.cleanup_messages(context)

async def delete_message_later(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int):
    await message_tracker.add_message(chat_id, message_id)

async def send_with_warning(message, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None, parse_mode=None):
    try:
        if hasattr(message, 'reply_text'):
            sent_message = await message.reply_text(
                f"{text}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await message.edit_text(
                f"{text}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

        await delete_message_later(context, sent_message.chat_id, sent_message.message_id)
        return sent_message
    except TelegramError as e:
        print(f"Error sending message: {e}")
        return None

async def send_photo_with_warning(message, context: ContextTypes.DEFAULT_TYPE, photo: str, caption: str, reply_markup=None, parse_mode=None):
    try:
        if hasattr(message, 'reply_photo'):
            sent_message = await message.reply_photo(
                photo=photo,
                caption=f"{caption}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await context.bot.send_photo(
                chat_id=message.chat_id,
                photo=photo,
                caption=f"{caption}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

        await delete_message_later(context, sent_message.chat_id, sent_message.message_id)
        return sent_message
    except TelegramError as e:
        print(f"Error sending photo: {e}")
        return None


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    keyboard = [
        [InlineKeyboardButton("  DOWNLOAD MOVIES", callback_data='search_movies')],
        [
            InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
            InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
            InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
        ],
        [InlineKeyboardButton("📈 Popular Movies", callback_data='popular'),
         InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
        [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
        [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_with_warning(
        update.message,
        context,
        f"👋 Hello {user_name}! Welcome to @movieshuba11_bot!\n\nClick on /start to restart or type",
        reply_markup=reply_markup
    )

async def show_start_menu(message, context: ContextTypes.DEFAULT_TYPE):
    # Get user's name from the callback query
    user_name = message._effective_user.first_name if hasattr(message, '_effective_user') else "there"
    keyboard = [
        [InlineKeyboardButton(" Download movies", callback_data='search_movies')],
        [
            InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
            InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
            InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
        ],
        [InlineKeyboardButton("📈 Popular Movies", callback_data='popular')],
        [InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
        [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
        [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_with_warning(
        message,
        context,
        f"👋 Hello {user_name}! Welcome to moviieshubb_bot!\n\nClick on /start to restart or type",
        reply_markup=reply_markup
    )



async def get_random_movies_by_genre(message, context: ContextTypes.DEFAULT_TYPE, genre_id=None):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "sort_by": "popularity.desc",
            "page": 1
        }

        if genre_id:
            params["with_genres"] = genre_id

        response = requests.get(url, params=params)
        response.raise_for_status()
        total_pages = min(response.json().get("total_pages", 1), 500)

        random_page = random.randint(1, total_pages)
        params["page"] = random_page

        response = requests.get(url, params=params)
        response.raise_for_status()

        all_movies = response.json().get("results", [])
        random_movies = random.sample(all_movies, min(5, len(all_movies)))

        response_text = "🎲 Random Movie Suggestions:\n\n"
        keyboard = []
        for i, movie in enumerate(random_movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"
            keyboard.append([InlineKeyboardButton(f"🔍 Search {movie['title']}", callback_data=f'search_specific_{movie["id"]}')])

        keyboard.extend([
            [
                InlineKeyboardButton("👻 Horror", callback_data='random_horror'),
                InlineKeyboardButton("🔪 Crime", callback_data='random_crime'),
                InlineKeyboardButton("💝 Romance", callback_data='random_romance')
            ],
            [InlineKeyboardButton("🎲 More Random", callback_data='random_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching random movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='random_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                                "Sorry, couldn't fetch random movies right now.",
                                reply_markup=reply_markup)


async def get_popular_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/movie/popular"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "🎬 Currently Popular Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching popular movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='popular')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch popular movies right now.",
                              reply_markup=reply_markup)

async def get_horror_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "with_genres": HORROR_GENRE_ID,
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "👻 Popular Horror Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton("👻 More Horror Movies", callback_data='horror_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching horror movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='horror_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch horror movies right now.",
                              reply_markup=reply_markup)

async def get_bollywood_popular_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "region": "IN",
            "with_original_language": "hi",
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "🎬  Bollywood Popular Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching Bollywood movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='bollywood_popular')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch Bollywood movies right now.",
                              reply_markup=reply_markup)


async def search_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    special_case, special_links = special_cases_manager.is_special_case(query)
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Log the search
    search_logger.log_search(user_id, user_name, "movie", query)
    try:
        tmdb_handler = TMDBAPIHandler(TMDB_API_KEY)

        # Search for movie
        results = tmdb_handler.make_request(
            "/search/movie",
            params={"query": query, "language": "en-US"}
        ).get("results", [])

        if results:
            movie = results[0]
            movie_id = movie["id"]

            # Get movie details
            movie_details = tmdb_handler.make_request(f"/movie/{movie_id}")
            providers = tmdb_handler.make_request(f"/movie/{movie_id}/watch/providers").get("results", {}).get("US",
                                                                                                               {}).get(
                "flatrate", [])

        search_url = f"{TMDB_BASE_URL}/search/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        if results:
            movie = results[0]
            movie_id = movie["id"]

            details_url = f"{TMDB_BASE_URL}/movie/{movie_id}"
            watch_providers_url = f"{TMDB_BASE_URL}/movie/{movie_id}/watch/providers"

            details_response = requests.get(details_url, params={"api_key": TMDB_API_KEY})
            providers_response = requests.get(watch_providers_url, params={"api_key": TMDB_API_KEY})

            movie_details = details_response.json()
            providers = providers_response.json().get("results", {}).get("US", {}).get("flatrate", [])

            keyboard = [
                [InlineKeyboardButton(" Search Another Movie", callback_data='search_movies')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            response_text = (
                f"*{movie_details['title']}* ({movie_details.get('release_date', '')[:4]})\n\n"
                f"Plot: {movie_details.get('overview', 'No plot available')}\n\n"
            )

            if providers:
                response_text += "Available on: " + ", ".join(p["provider_name"] for p in providers) + "\n\n"
            else:
                response_text += "Streaming information not available\n\n"

            if special_case and special_links:
                response_text += "Download Links:\n"
                for link in special_links:
                    lang_text = f" ({link['language']})" if link.get('language') else ""
                    response_text += f"• {link['url']}{lang_text}\n"
            else:
                response_text += "download link comming soon msg @balaram129"

            if movie_details.get("poster_path"):
                poster_url = f"{TMDB_IMAGE_BASE_URL}{movie_details['poster_path']}"
                await send_photo_with_warning(update.message, context, photo=poster_url, caption=response_text, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                await send_with_warning(update.message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            keyboard = [
                [InlineKeyboardButton(" Try Again", callback_data='search_movies')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(update.message, context, "No movies found matching your search.", reply_markup=reply_markup)
    except Exception as e:
        print(f"Error in movie search: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(update.message, context,
                              "Sorry, there was an error processing your request. Please try again.",
                              reply_markup=reply_markup)

async def search_by_actor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Log the search
    search_logger.log_search(user_id, user_name, "actor", query)
    try:
        search_url = f"{TMDB_BASE_URL}/search/person"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        if results:
            actor = results[0]
            actor_id = actor["id"]

            actor_details_url = f"{TMDB_BASE_URL}/person/{actor_id}"
            movies_url = f"{TMDB_BASE_URL}/person/{actor_id}/movie_credits"

            actor_details_response = requests.get(actor_details_url, params={"api_key": TMDB_API_KEY})
            movies_response = requests.get(movies_url, params={"api_key": TMDB_API_KEY})

            actor_details = actor_details_response.json()
            movies = movies_response.json().get("cast", [])

            movies_with_rating = [m for m in movies if m.get("vote_average", 0) > 0]
            sorted_movies = sorted(movies_with_rating, key=lambda x: x.get("vote_average", 0), reverse=True)

            popular_movies = [m for m in sorted_movies if m.get("vote_average", 0) >= 7][:4]
            unpopular_movies = [m for m in sorted_movies if m.get("vote_average", 0) < 7][:4]

            response_text = f"🎭 {actor['name']}\n"
            if actor_details.get("birthday"):
                response_text += f"Birthday: {actor_details['birthday']}\n"
            if actor_details.get("place_of_birth"):
                response_text += f"Birthplace: {actor_details['place_of_birth']}\n"

            response_text += "\n📈 Highly Rated Movies:\n"
            for i, movie in enumerate(popular_movies, 1):
                response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
                response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"

            response_text += "\n📉 Other Notable Movies:\n"
            for i, movie in enumerate(unpopular_movies, 1):
                response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
                response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"

            keyboard = [
                [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
                [InlineKeyboardButton(" Search Another Actor", callback_data='search_actor')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            if actor.get("profile_path"):
                actor_image_url = f"{TMDB_IMAGE_BASE_URL}{actor['profile_path']}"
                await send_photo_with_warning(
                    update.message,
                    context,
                    photo=actor_image_url,
                    caption=response_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await send_with_warning(
                    update.message,
                    context,
                    response_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
        else:
            keyboard = [
                [InlineKeyboardButton(" Try Again", callback_data='search_actor')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                update.message,
                context,
                "No actor found matching your search.",
                reply_markup=reply_markup
            )
    except Exception as e:
        print(f"Error in actor search: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='search_actor')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(
            update.message,
            context,
            "Sorry, there was an error processing your request. Please try again.",
            reply_markup=reply_markup
        )
def is_special_case(query):
    query_lower = query.lower().strip()
    for key, case in special_cases_manager.items():
        if query_lower == key.lower() or query_lower in [v.lower() for v in case["variants"]]:
            return True, case["links"]
    return False, []

async def get_genre_movies(message, context: ContextTypes.DEFAULT_TYPE, genre_id: int, genre_name: str):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "with_genres": genre_id,
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = f"🎬 Popular {genre_name} Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching {genre_name} movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data=f'genre_{genre_name.lower()}')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              f"Sorry, couldn't fetch {genre_name} movies right now.",
                              reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_name = query.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    try:
        if query.data.startswith('search_specific_'):
            movie_id = query.data.split('_')[2]
            # Get movie details from TMDB
            url = f"{TMDB_BASE_URL}/movie/{movie_id}"
            response = requests.get(url, params={"api_key": TMDB_API_KEY})
            movie = response.json()

            # Create a message with movie details
            movie_text = f"{movie['title']} ({movie.get('release_date', '')[:4]})"

            # Send a temporary message to user's private chat
            class SimulatedMessage:
                def __init__(self, chat_id, text, from_user):
                    self.chat_id = chat_id
                    self.text = text
                    self.from_user = from_user

                def reply_text(self, *args, **kwargs):
                    return query.message.reply_text(*args, **kwargs)

                def reply_photo(self, *args, **kwargs):
                    return query.message.reply_photo(*args, **kwargs)

            # Create a proper message object
            simulated_message = SimulatedMessage(
                chat_id=query.message.chat_id,
                text=movie['title'],
                from_user=query.from_user
            )

            # Create a proper update object
            class SimulatedUpdate:
                def __init__(self, message):
                    self.message = message

            simulated_update = SimulatedUpdate(simulated_message)

            # Perform the search
            await search_movie(simulated_update, context)
            return
        if query.data == 'genre_horror':
            await get_genre_movies(query.message, context, GENRE_IDS['horror'], "Horror")
        elif query.data == 'genre_romance':
            await get_genre_movies(query.message, context, GENRE_IDS['romance'], "Romance")
        elif query.data == 'genre_crime':
            await get_genre_movies(query.message, context, GENRE_IDS['crime'], "Crime")
        elif query.data == 'random_movies':
            await get_random_movies_by_genre(query.message, context)
        if query.data == 'random_movies':
            await get_random_movies_by_genre(query.message, context)
        elif query.data == 'random_horror':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['horror'])
        elif query.data == 'random_crime':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['crime'])
        elif query.data == 'random_romance':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['romance'])
        elif query.data == 'horror_movies':
            await get_horror_movies(query.message, context)
        elif query.data == 'search_movies':
            USER_CONTEXT[query.message.chat_id] = 'movie'
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "🔍 Just type the name of any movie you want to search for!",
                reply_markup=reply_markup
            )
        elif query.data == 'search_actor':
            USER_CONTEXT[query.message.chat_id] = 'actor'
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "🎭 Just type the name of any actor to see their movies!",
                reply_markup=reply_markup
            )
        elif query.data == 'help':
            help_text = ("📖 How to use this bot:\n\n"
                        "1. Simply type any movie name\n"
                        "2. Or type any actor name to find their movies\n"
                        "3. I'll show you the details\n"
                        "4. Check out popular movies in both Hollywood and Bollywood\n"
                        "5. Try our random movie suggestions by genre!\n"
                        "Need more help? Just type /start to see the main menu again! or msg @balaram129")
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                help_text,
                reply_markup=reply_markup
            )
        elif query.data == 'popular':
            await get_popular_movies(query.message, context)
        elif query.data == 'bollywood_popular':
            await get_bollywood_popular_movies(query.message, context)
        elif query.data == 'start_menu':
            keyboard = [
                [InlineKeyboardButton("🔍 Download movies", callback_data='search_movies'),
                 InlineKeyboardButton("👻 Horror Movies", callback_data='horror_movies')],
                [
                    InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
                    InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
                    InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
                ],
                [InlineKeyboardButton("📈 Popular Movies", callback_data='popular')],
                [InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
                [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
                [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
                [InlineKeyboardButton("❓ Help", callback_data='help')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "👋 Welcome to moviieshubb_bot!\n\nClick on /start to restart or type",
                reply_markup=reply_markup
            )

    except Exception as e:
        print(f"Error in button callback: {e}")
        keyboard = [
            [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(
            query.message,
            context,
            "Sorry, there was an error processing your request. Please try again.",
            reply_markup=reply_markup
        )

async def handle_user_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_context = USER_CONTEXT.get(update.message.chat_id, "movie")
    if user_context == "actor":
        await search_by_actor(update, context)
    else:
        await search_movie(update, context)

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_message_later(context, update.message.chat_id, update.message.message_id)
    await handle_user_query(update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Exception while handling an update: {context.error}")
    if isinstance(context.error, Conflict):
        print("Bot instance already running. Exiting...")
        sys.exit(1)
    elif isinstance(context.error, NetworkError):
        print("Network error occurred. Waiting before retry...")
        await asyncio.sleep(1)
    else:
        print(f"Unexpected error: {context.error}")


def main():
    try:
        application = (
            Application.builder()
            .token(TELEGRAM_TOKEN)
            .build()
        )

        # Add existing handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CallbackQueryHandler(button_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))
        application.add_handler(CommandHandler("viewsearches", view_searches_command))

        # Add error handler
        application.add_error_handler(error_handler)

        # Set up the cleanup job to run every 10 seconds
        job_queue = application.job_queue
        job_queue.run_repeating(cleanup_job, interval=10, first=0)

        # Add the inactive user check job (runs every 6 hours)
        job_queue.run_repeating(check_inactive_users, interval=21600, first=21600)

        # Update stastics more frequently (every 5 minutes)
        job_queue.run_repeating(update_stastics_job, interval=300, first=0)

        # Initial statistics update
        print("Performing initial statistics update...")
        stats = SearchStatistics()
        stats.update_stastics_file()
        print("Initial statistics update completed")

        # Start the bot
        print("Starting bot...")
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

    except Exception as e:
        print(f"Error starting bot: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

# Test the logger
logger = SearchLogger()
logger.log_search(123456, "TestUser", "movie", "Avatar")

# Check recent searches
recent = logger.get_recent_searches()
print("Recent searches:", recent)import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import Conflict, NetworkError, TelegramError
import nest_asyncio
import sys
import random
from typing import Optional, Dict
from datetime import datetime, timedelta
import pickle
from special_cases_managerss import SpecialCasesManager
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import json
from datetime import datetime
from pathlib import Path


class SearchLogger:
    def __init__(self, log_file="search_logs.json"):
        self.log_file = log_file
        self.ensure_log_file_exists()

    def ensure_log_file_exists(self):
        # Create the file with an empty list if it doesn't exist or is empty
        if not Path(self.log_file).exists() or Path(self.log_file).stat().st_size == 0:
            with open(self.log_file, 'w') as f:
                json.dump([], f)

    def log_search(self, user_id: int, user_name: str, search_type: str, search_query: str):
        try:
            # First ensure the file exists and has valid JSON
            self.ensure_log_file_exists()

            # Read existing logs
            try:
                with open(self.log_file, 'r') as f:
                    logs = json.load(f)
            except json.JSONDecodeError:
                # If there's an error reading the JSON, start with an empty list
                logs = []

            # Create new log entry
            log_entry = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "user_id": user_id,
                "user_name": user_name,
                "search_type": search_type,
                "search_query": search_query
            }

            # Add new entry
            logs.append(log_entry)

            # Write back to file
            with open(self.log_file, 'w') as f:
                json.dump(logs, f, indent=2)

        except Exception as e:
            print(f"Error logging search: {e}")

    def get_recent_searches(self, limit: int = 100):
        try:
            # First ensure the file exists and has valid JSON
            self.ensure_log_file_exists()

            with open(self.log_file, 'r') as f:
                try:
                    logs = json.load(f)
                except json.JSONDecodeError:
                    return []
            return logs[-limit:]
        except Exception as e:
            print(f"Error getting recent searches: {e}")
            return []


# Create an instance of the logger
search_logger = SearchLogger()


# After your other global variables
special_cases_manager = SpecialCasesManager()

# Initialize some cases if you want (optional)
special_cases_manager.add_case(
    "pushpa 2",
    ["pushpa2", "pushpa-2", "pushpa2therule", "pushpa 2 the rule"],
    [
        {"url": "https://example4.com", "language": "Hindi"},
        {"url": "https://example5.com", "language": "Telugu"}
    ]
)

special_cases_manager.add_case(
    "venom",
    ["venom", "venom1", "venom2"],
    [
        {"url": "https://www.udlinks.com/3I1l", "language": "hindi"}
    ]
)




nest_asyncio.apply()

TELEGRAM_TOKEN = "7883754025:AAHUDU-_EM4QYome14k_28PQbPTWsl_9w6s"
TMDB_API_KEY = "c3b8704a4df65146c194940351efa9a2"
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
DELETE_TIMEOUT = 420  # 7 minutes in seconds
DISCLAIMER = "⚠️ This message will be deleted in 7 minutes"
HORROR_GENRE_ID = 27  # TMDB's genre ID for horror movies



USER_CONTEXT = {}

GENRE_IDS = {
    'horror': 27,
    'crime': 80,
    'romance': 10749
}


class TMDBAPIHandler:
    def __init__(self, api_key, base_url="https://api.themoviedb.org/3"):
        self.api_key = api_key
        self.base_url = base_url
        self.session = self._create_session()

    def _create_session(self):
        session = requests.Session()

        # Configure retry strategy
        retries = Retry(
            total=5,  # Total number of retries
            backoff_factor=0.5,  # Wait 0.5, 1, 2, 4, 8 seconds between retries
            status_forcelist=[500, 502, 503, 504, 408, 429]  # HTTP status codes to retry on
        )

        # Add retry adapter to session
        adapter = HTTPAdapter(max_retries=retries)
        session.mount('http://', adapter)
        session.mount('https://', adapter)

        return session

    def make_request(self, endpoint, params=None):
        if params is None:
            params = {}

        # Always include API key
        params['api_key'] = self.api_key

        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                response = self.session.get(
                    f"{self.base_url}{endpoint}",
                    params=params,
                    timeout=10  # 10 seconds timeout
                )
                response.raise_for_status()
                return response.json()

            except requests.exceptions.ConnectionError as e:
                if attempt == max_attempts - 1:
                    raise Exception("Unable to connect to TMDB API. Please check your internet connection.") from e
                time.sleep(2 ** attempt)  # Exponential backoff

            except requests.exceptions.Timeout as e:
                if attempt == max_attempts - 1:
                    raise Exception("TMDB API request timed out. Please try again later.") from e
                time.sleep(2 ** attempt)

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:  # Rate limit exceeded
                    retry_after = int(e.response.headers.get('Retry-After', 5))
                    time.sleep(retry_after)
                    continue
                raise Exception(f"TMDB API error: {e.response.status_code}") from e


LAST_ACTIVITY_FILE = "user_activity.pkl"
INACTIVITY_THRESHOLD = timedelta(hours=78)


class SearchStatistics:
    def __init__(self, log_file="search_logs.json", stats_file="stastics.txt"):
        self.log_file = log_file
        self.stats_file = stats_file
        self.search_logger = SearchLogger(log_file)
        # Ensure stastics file exists
        self.update_stastics_file()
        print(f"SearchStatistics initialized. Stats file: {stats_file}")

    def _load_searches(self):
        """Load searches from the log file"""
        try:
            with open(self.log_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def get_most_searched(self, days=None):
        """Get most searched queries within specified days"""
        searches = self._load_searches()
        if not searches:
            return []

        # Filter by date if days is specified
        if days:
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            searches = [s for s in searches if s['timestamp'][:10] >= cutoff_date]

        # Count search queries
        query_counts = {}
        for search in searches:
            query = search['search_query'].lower()
            query_counts[query] = query_counts.get(query, 0) + 1

        # Sort by count and return top 10
        return sorted(query_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    def get_user_search_history(self, limit=50):
        """Get recent user search history"""
        searches = self._load_searches()
        return searches[-limit:] if searches else []

    def update_stastics_file(self):  # Changed method name to match file name
        try:
            print(f"Updating stastics file at {datetime.now()}")

            # Check if log file exists and has data
            if not Path(self.log_file).exists():
                print(f"Log file {self.log_file} does not exist!")
                return

            # Load searches
            searches = self._load_searches()
            if not searches:
                print("No search data found in logs")
                stats_text = "No search data available yet.\nLast Updated: " + datetime.now().strftime(
                    '%Y-%m-%d %H:%M:%S')
            else:
                # Get statistics for different time periods
                all_time = self.get_most_searched()
                today = self.get_most_searched(days=1)
                week = self.get_most_searched(days=7)
                year = self.get_most_searched(days=365)
                user_history = self.get_user_search_history(limit=50)

                stats_text = self._format_stastics(all_time, today, week, year, user_history)  # Changed method name

            # Write to stastics file
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                f.write(stats_text)

            print(f"Stastics file updated successfully at {datetime.now()}")

            # Debug: Read and print file contents
            with open(self.stats_file, 'r', encoding='utf-8') as f:
                content = f.read()
            print(f"Stastics file size: {len(content)} bytes")

        except Exception as e:
            print(f"Error updating stastics file: {e}")
            import traceback
            traceback.print_exc()

    def _format_stastics(self, all_time, today, week, year, user_history):  # Changed method name
        stats_text = "Movie Search Stastics\n"  # Changed heading
        stats_text += "=" * 50 + "\n\n"

        # Add section for each time period
        sections = [
            ("All-Time Most Searched Movies:", all_time),
            ("Today's Most Searched Movies:", today),
            ("This Week's Most Searched Movies:", week),
            ("This Year's Most Searched Movies:", year)
        ]

        for title, data in sections:
            stats_text += f"{title}\n"
            if data:
                stats_text += "\n".join(f"{i + 1}. {movie} ({count} searches)"
                                      for i, (movie, count) in enumerate(data))
            else:
                stats_text += "No searches in this period"
            stats_text += "\n\n"

        # Add user history section
        stats_text += "Recent User Search History:\n"
        stats_text += "=" * 50 + "\n"
        if user_history:
            for search in user_history:
                stats_text += f"\nTime: {search['timestamp']}\n"
                stats_text += f"User: {search['user_name']} (ID: {search['user_id']})\n"
                stats_text += f"Search Type: {search['search_type']}\n"
                stats_text += f"Query: {search['search_query']}\n"
                stats_text += "-" * 30 + "\n"
        else:
            stats_text += "\nNo user search history available yet\n"

        stats_text += f"\nLast Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        return stats_text

# Modify the update_statistics_job to include error handling and logging
async def update_stastics_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        print(f"Starting stastics update job at {datetime.now()}")
        stats = SearchStatistics()
        stats.update_stastics_file()
        print(f"Completed stastics update job at {datetime.now()}")
    except Exception as e:
        print(f"Error in stastics update job: {e}")
        import traceback
        traceback.print_exc()

async def view_searches_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only allow yourself to see the searches
    if update.message.from_user.id == 6822829183:  # Replace with your Telegram ID
        recent_searches = search_logger.get_recent_searches(limit=10)  # Get last 10 searches

        message = "Recent Searches:\n\n"
        for search in recent_searches:
            message += f"👤 User: {search['user_name']}\n"
            message += f"🔍 Query: {search['search_query']}\n"
            message += f"⏰ Time: {search['timestamp']}\n"
            message += f"Type: {search['search_type']}\n\n"

        await update.message.reply_text(message)
    else:
        await update.message.reply_text("You don't have permission to use this command.")


# Add this to your command handlers

class UserActivityManager:
    def __init__(self):
        self.user_activity = {}
        self.load_activity()

    def load_activity(self):
        if Path(LAST_ACTIVITY_FILE).exists():
            try:
                with open(LAST_ACTIVITY_FILE, 'rb') as f:
                    self.user_activity = pickle.load(f)
            except Exception as e:
                print(f"Error loading user activity: {e}")
                self.user_activity = {}

    def save_activity(self):
        try:
            with open(LAST_ACTIVITY_FILE, 'wb') as f:
                pickle.dump(self.user_activity, f)
        except Exception as e:
            print(f"Error saving user activity: {e}")

    def update_user_activity(self, user_id: int, user_name: str):
        self.user_activity[user_id] = {
            'last_active': datetime.now(),
            'name': user_name
        }
        self.save_activity()

    def get_inactive_users(self):
        current_time = datetime.now()
        inactive_users = []

        for user_id, data in self.user_activity.items():
            if (current_time - data['last_active']) >= INACTIVITY_THRESHOLD:
                inactive_users.append({
                    'user_id': user_id,
                    'name': data['name'],
                    'last_active': data['last_active']
                })

        return inactive_users


# Create global instance
activity_manager = UserActivityManager()


# Modify the handle_user_message function to track activity
async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    await delete_message_later(context, update.message.chat_id, update.message.message_id)
    await handle_user_query(update, context)


# Add a new function to check for inactive users
async def check_inactive_users(context: ContextTypes.DEFAULT_TYPE):
    inactive_users = activity_manager.get_inactive_users()

    for user in inactive_users:
        try:
            message = f"Hey {user['name']} 👋,\n\nI am missing you dear! 💫\nIt's been a while since we last chatted. Come back and discover some amazing movies! 🎬"

            await context.bot.send_message(
                chat_id=user['user_id'],
                text=message,
                parse_mode='Markdown'
            )

            # Update the last activity to prevent spam
            activity_manager.update_user_activity(user['user_id'], user['name'])

        except Exception as e:
            print(f"Error sending reminder to user {user['user_id']}: {e}")

class MessageTracker:
    def __init__(self):
        self.messages: Dict[int, Dict[int, datetime]] = {}

    async def add_message(self, chat_id: int, message_id: int):
        if chat_id not in self.messages:
            self.messages[chat_id] = {}
        self.messages[chat_id][message_id] = datetime.now() + timedelta(seconds=DELETE_TIMEOUT)

    async def cleanup_messages(self, context: ContextTypes.DEFAULT_TYPE):
        current_time = datetime.now()
        for chat_id in list(self.messages.keys()):
            for message_id, expiry_time in list(self.messages[chat_id].items()):
                if current_time >= expiry_time:
                    try:
                        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                    except TelegramError:
                        pass  # Message might already be deleted
                    finally:
                        del self.messages[chat_id][message_id]
            if not self.messages[chat_id]:
                del self.messages[chat_id]

message_tracker = MessageTracker()

async def cleanup_job(context: ContextTypes.DEFAULT_TYPE):
    await message_tracker.cleanup_messages(context)

async def delete_message_later(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int):
    await message_tracker.add_message(chat_id, message_id)

async def send_with_warning(message, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None, parse_mode=None):
    try:
        if hasattr(message, 'reply_text'):
            sent_message = await message.reply_text(
                f"{text}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await message.edit_text(
                f"{text}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

        await delete_message_later(context, sent_message.chat_id, sent_message.message_id)
        return sent_message
    except TelegramError as e:
        print(f"Error sending message: {e}")
        return None

async def send_photo_with_warning(message, context: ContextTypes.DEFAULT_TYPE, photo: str, caption: str, reply_markup=None, parse_mode=None):
    try:
        if hasattr(message, 'reply_photo'):
            sent_message = await message.reply_photo(
                photo=photo,
                caption=f"{caption}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await context.bot.send_photo(
                chat_id=message.chat_id,
                photo=photo,
                caption=f"{caption}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

        await delete_message_later(context, sent_message.chat_id, sent_message.message_id)
        return sent_message
    except TelegramError as e:
        print(f"Error sending photo: {e}")
        return None


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    keyboard = [
        [InlineKeyboardButton("  DOWNLOAD MOVIES", callback_data='search_movies')],
        [
            InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
            InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
            InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
        ],
        [InlineKeyboardButton("📈 Popular Movies", callback_data='popular'),
         InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
        [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
        [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_with_warning(
        update.message,
        context,
        f"👋 Hello {user_name}! Welcome to @movieshuba11_bot!\n\nClick on /start to restart or type",
        reply_markup=reply_markup
    )

async def show_start_menu(message, context: ContextTypes.DEFAULT_TYPE):
    # Get user's name from the callback query
    user_name = message._effective_user.first_name if hasattr(message, '_effective_user') else "there"
    keyboard = [
        [InlineKeyboardButton(" Download movies", callback_data='search_movies')],
        [
            InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
            InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
            InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
        ],
        [InlineKeyboardButton("📈 Popular Movies", callback_data='popular')],
        [InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
        [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
        [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_with_warning(
        message,
        context,
        f"👋 Hello {user_name}! Welcome to moviieshubb_bot!\n\nClick on /start to restart or type",
        reply_markup=reply_markup
    )



async def get_random_movies_by_genre(message, context: ContextTypes.DEFAULT_TYPE, genre_id=None):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "sort_by": "popularity.desc",
            "page": 1
        }

        if genre_id:
            params["with_genres"] = genre_id

        response = requests.get(url, params=params)
        response.raise_for_status()
        total_pages = min(response.json().get("total_pages", 1), 500)

        random_page = random.randint(1, total_pages)
        params["page"] = random_page

        response = requests.get(url, params=params)
        response.raise_for_status()

        all_movies = response.json().get("results", [])
        random_movies = random.sample(all_movies, min(5, len(all_movies)))

        response_text = "🎲 Random Movie Suggestions:\n\n"
        keyboard = []
        for i, movie in enumerate(random_movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"
            keyboard.append([InlineKeyboardButton(f"🔍 Search {movie['title']}", callback_data=f'search_specific_{movie["id"]}')])

        keyboard.extend([
            [
                InlineKeyboardButton("👻 Horror", callback_data='random_horror'),
                InlineKeyboardButton("🔪 Crime", callback_data='random_crime'),
                InlineKeyboardButton("💝 Romance", callback_data='random_romance')
            ],
            [InlineKeyboardButton("🎲 More Random", callback_data='random_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching random movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='random_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                                "Sorry, couldn't fetch random movies right now.",
                                reply_markup=reply_markup)


async def get_popular_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/movie/popular"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "🎬 Currently Popular Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching popular movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='popular')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch popular movies right now.",
                              reply_markup=reply_markup)

async def get_horror_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "with_genres": HORROR_GENRE_ID,
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "👻 Popular Horror Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton("👻 More Horror Movies", callback_data='horror_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching horror movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='horror_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch horror movies right now.",
                              reply_markup=reply_markup)

async def get_bollywood_popular_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "region": "IN",
            "with_original_language": "hi",
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "🎬  Bollywood Popular Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching Bollywood movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='bollywood_popular')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch Bollywood movies right now.",
                              reply_markup=reply_markup)


async def search_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    special_case, special_links = special_cases_manager.is_special_case(query)
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Log the search
    search_logger.log_search(user_id, user_name, "movie", query)
    try:
        tmdb_handler = TMDBAPIHandler(TMDB_API_KEY)

        # Search for movie
        results = tmdb_handler.make_request(
            "/search/movie",
            params={"query": query, "language": "en-US"}
        ).get("results", [])

        if results:
            movie = results[0]
            movie_id = movie["id"]

            # Get movie details
            movie_details = tmdb_handler.make_request(f"/movie/{movie_id}")
            providers = tmdb_handler.make_request(f"/movie/{movie_id}/watch/providers").get("results", {}).get("US",
                                                                                                               {}).get(
                "flatrate", [])

        search_url = f"{TMDB_BASE_URL}/search/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        if results:
            movie = results[0]
            movie_id = movie["id"]

            details_url = f"{TMDB_BASE_URL}/movie/{movie_id}"
            watch_providers_url = f"{TMDB_BASE_URL}/movie/{movie_id}/watch/providers"

            details_response = requests.get(details_url, params={"api_key": TMDB_API_KEY})
            providers_response = requests.get(watch_providers_url, params={"api_key": TMDB_API_KEY})

            movie_details = details_response.json()
            providers = providers_response.json().get("results", {}).get("US", {}).get("flatrate", [])

            keyboard = [
                [InlineKeyboardButton(" Search Another Movie", callback_data='search_movies')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            response_text = (
                f"*{movie_details['title']}* ({movie_details.get('release_date', '')[:4]})\n\n"
                f"Plot: {movie_details.get('overview', 'No plot available')}\n\n"
            )

            if providers:
                response_text += "Available on: " + ", ".join(p["provider_name"] for p in providers) + "\n\n"
            else:
                response_text += "Streaming information not available\n\n"

            if special_case and special_links:
                response_text += "Download Links:\n"
                for link in special_links:
                    lang_text = f" ({link['language']})" if link.get('language') else ""
                    response_text += f"• {link['url']}{lang_text}\n"
            else:
                response_text += "download link comming soon msg @balaram129"

            if movie_details.get("poster_path"):
                poster_url = f"{TMDB_IMAGE_BASE_URL}{movie_details['poster_path']}"
                await send_photo_with_warning(update.message, context, photo=poster_url, caption=response_text, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                await send_with_warning(update.message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            keyboard = [
                [InlineKeyboardButton(" Try Again", callback_data='search_movies')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(update.message, context, "No movies found matching your search.", reply_markup=reply_markup)
    except Exception as e:
        print(f"Error in movie search: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(update.message, context,
                              "Sorry, there was an error processing your request. Please try again.",
                              reply_markup=reply_markup)

async def search_by_actor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Log the search
    search_logger.log_search(user_id, user_name, "actor", query)
    try:
        search_url = f"{TMDB_BASE_URL}/search/person"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        if results:
            actor = results[0]
            actor_id = actor["id"]

            actor_details_url = f"{TMDB_BASE_URL}/person/{actor_id}"
            movies_url = f"{TMDB_BASE_URL}/person/{actor_id}/movie_credits"

            actor_details_response = requests.get(actor_details_url, params={"api_key": TMDB_API_KEY})
            movies_response = requests.get(movies_url, params={"api_key": TMDB_API_KEY})

            actor_details = actor_details_response.json()
            movies = movies_response.json().get("cast", [])

            movies_with_rating = [m for m in movies if m.get("vote_average", 0) > 0]
            sorted_movies = sorted(movies_with_rating, key=lambda x: x.get("vote_average", 0), reverse=True)

            popular_movies = [m for m in sorted_movies if m.get("vote_average", 0) >= 7][:4]
            unpopular_movies = [m for m in sorted_movies if m.get("vote_average", 0) < 7][:4]

            response_text = f"🎭 {actor['name']}\n"
            if actor_details.get("birthday"):
                response_text += f"Birthday: {actor_details['birthday']}\n"
            if actor_details.get("place_of_birth"):
                response_text += f"Birthplace: {actor_details['place_of_birth']}\n"

            response_text += "\n📈 Highly Rated Movies:\n"
            for i, movie in enumerate(popular_movies, 1):
                response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
                response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"

            response_text += "\n📉 Other Notable Movies:\n"
            for i, movie in enumerate(unpopular_movies, 1):
                response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
                response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"

            keyboard = [
                [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
                [InlineKeyboardButton(" Search Another Actor", callback_data='search_actor')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            if actor.get("profile_path"):
                actor_image_url = f"{TMDB_IMAGE_BASE_URL}{actor['profile_path']}"
                await send_photo_with_warning(
                    update.message,
                    context,
                    photo=actor_image_url,
                    caption=response_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await send_with_warning(
                    update.message,
                    context,
                    response_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
        else:
            keyboard = [
                [InlineKeyboardButton(" Try Again", callback_data='search_actor')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                update.message,
                context,
                "No actor found matching your search.",
                reply_markup=reply_markup
            )
    except Exception as e:
        print(f"Error in actor search: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='search_actor')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(
            update.message,
            context,
            "Sorry, there was an error processing your request. Please try again.",
            reply_markup=reply_markup
        )
def is_special_case(query):
    query_lower = query.lower().strip()
    for key, case in special_cases_manager.items():
        if query_lower == key.lower() or query_lower in [v.lower() for v in case["variants"]]:
            return True, case["links"]
    return False, []

async def get_genre_movies(message, context: ContextTypes.DEFAULT_TYPE, genre_id: int, genre_name: str):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "with_genres": genre_id,
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = f"🎬 Popular {genre_name} Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching {genre_name} movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data=f'genre_{genre_name.lower()}')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              f"Sorry, couldn't fetch {genre_name} movies right now.",
                              reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_name = query.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    try:
        if query.data.startswith('search_specific_'):
            movie_id = query.data.split('_')[2]
            # Get movie details from TMDB
            url = f"{TMDB_BASE_URL}/movie/{movie_id}"
            response = requests.get(url, params={"api_key": TMDB_API_KEY})
            movie = response.json()

            # Create a message with movie details
            movie_text = f"{movie['title']} ({movie.get('release_date', '')[:4]})"

            # Send a temporary message to user's private chat
            class SimulatedMessage:
                def __init__(self, chat_id, text, from_user):
                    self.chat_id = chat_id
                    self.text = text
                    self.from_user = from_user

                def reply_text(self, *args, **kwargs):
                    return query.message.reply_text(*args, **kwargs)

                def reply_photo(self, *args, **kwargs):
                    return query.message.reply_photo(*args, **kwargs)

            # Create a proper message object
            simulated_message = SimulatedMessage(
                chat_id=query.message.chat_id,
                text=movie['title'],
                from_user=query.from_user
            )

            # Create a proper update object
            class SimulatedUpdate:
                def __init__(self, message):
                    self.message = message

            simulated_update = SimulatedUpdate(simulated_message)

            # Perform the search
            await search_movie(simulated_update, context)
            return
        if query.data == 'genre_horror':
            await get_genre_movies(query.message, context, GENRE_IDS['horror'], "Horror")
        elif query.data == 'genre_romance':
            await get_genre_movies(query.message, context, GENRE_IDS['romance'], "Romance")
        elif query.data == 'genre_crime':
            await get_genre_movies(query.message, context, GENRE_IDS['crime'], "Crime")
        elif query.data == 'random_movies':
            await get_random_movies_by_genre(query.message, context)
        if query.data == 'random_movies':
            await get_random_movies_by_genre(query.message, context)
        elif query.data == 'random_horror':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['horror'])
        elif query.data == 'random_crime':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['crime'])
        elif query.data == 'random_romance':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['romance'])
        elif query.data == 'horror_movies':
            await get_horror_movies(query.message, context)
        elif query.data == 'search_movies':
            USER_CONTEXT[query.message.chat_id] = 'movie'
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "🔍 Just type the name of any movie you want to search for!",
                reply_markup=reply_markup
            )
        elif query.data == 'search_actor':
            USER_CONTEXT[query.message.chat_id] = 'actor'
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "🎭 Just type the name of any actor to see their movies!",
                reply_markup=reply_markup
            )
        elif query.data == 'help':
            help_text = ("📖 How to use this bot:\n\n"
                        "1. Simply type any movie name\n"
                        "2. Or type any actor name to find their movies\n"
                        "3. I'll show you the details\n"
                        "4. Check out popular movies in both Hollywood and Bollywood\n"
                        "5. Try our random movie suggestions by genre!\n"
                        "Need more help? Just type /start to see the main menu again! or msg @balaram129")
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                help_text,
                reply_markup=reply_markup
            )
        elif query.data == 'popular':
            await get_popular_movies(query.message, context)
        elif query.data == 'bollywood_popular':
            await get_bollywood_popular_movies(query.message, context)
        elif query.data == 'start_menu':
            keyboard = [
                [InlineKeyboardButton("🔍 Download movies", callback_data='search_movies'),
                 InlineKeyboardButton("👻 Horror Movies", callback_data='horror_movies')],
                [
                    InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
                    InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
                    InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
                ],
                [InlineKeyboardButton("📈 Popular Movies", callback_data='popular')],
                [InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
                [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
                [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
                [InlineKeyboardButton("❓ Help", callback_data='help')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "👋 Welcome to moviieshubb_bot!\n\nClick on /start to restart or type",
                reply_markup=reply_markup
            )

    except Exception as e:
        print(f"Error in button callback: {e}")
        keyboard = [
            [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(
            query.message,
            context,
            "Sorry, there was an error processing your request. Please try again.",
            reply_markup=reply_markup
        )

async def handle_user_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_context = USER_CONTEXT.get(update.message.chat_id, "movie")
    if user_context == "actor":
        await search_by_actor(update, context)
    else:
        await search_movie(update, context)

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_message_later(context, update.message.chat_id, update.message.message_id)
    await handle_user_query(update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Exception while handling an update: {context.error}")
    if isinstance(context.error, Conflict):
        print("Bot instance already running. Exiting...")
        sys.exit(1)
    elif isinstance(context.error, NetworkError):
        print("Network error occurred. Waiting before retry...")
        await asyncio.sleep(1)
    else:
        print(f"Unexpected error: {context.error}")


def main():
    try:
        application = (
            Application.builder()
            .token(TELEGRAM_TOKEN)
            .build()
        )

        # Add existing handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CallbackQueryHandler(button_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))
        application.add_handler(CommandHandler("viewsearches", view_searches_command))

        # Add error handler
        application.add_error_handler(error_handler)

        # Set up the cleanup job to run every 10 seconds
        job_queue = application.job_queue
        job_queue.run_repeating(cleanup_job, interval=10, first=0)

        # Add the inactive user check job (runs every 6 hours)
        job_queue.run_repeating(check_inactive_users, interval=21600, first=21600)

        # Update stastics more frequently (every 5 minutes)
        job_queue.run_repeating(update_stastics_job, interval=300, first=0)

        # Initial statistics update
        print("Performing initial statistics update...")
        stats = SearchStatistics()
        stats.update_stastics_file()
        print("Initial statistics update completed")

        # Start the bot
        print("Starting bot...")
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

    except Exception as e:
        print(f"Error starting bot: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

# Test the logger
logger = SearchLogger()
logger.log_search(123456, "TestUser", "movie", "Avatar")

# Check recent searches
recent = logger.get_recent_searches()
print("Recent searches:", recent)import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import Conflict, NetworkError, TelegramError
import nest_asyncio
import sys
import random
from typing import Optional, Dict
from datetime import datetime, timedelta
import pickle
from special_cases_managerss import SpecialCasesManager
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import json
from datetime import datetime
from pathlib import Path


class SearchLogger:
    def __init__(self, log_file="search_logs.json"):
        self.log_file = log_file
        self.ensure_log_file_exists()

    def ensure_log_file_exists(self):
        # Create the file with an empty list if it doesn't exist or is empty
        if not Path(self.log_file).exists() or Path(self.log_file).stat().st_size == 0:
            with open(self.log_file, 'w') as f:
                json.dump([], f)

    def log_search(self, user_id: int, user_name: str, search_type: str, search_query: str):
        try:
            # First ensure the file exists and has valid JSON
            self.ensure_log_file_exists()

            # Read existing logs
            try:
                with open(self.log_file, 'r') as f:
                    logs = json.load(f)
            except json.JSONDecodeError:
                # If there's an error reading the JSON, start with an empty list
                logs = []

            # Create new log entry
            log_entry = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "user_id": user_id,
                "user_name": user_name,
                "search_type": search_type,
                "search_query": search_query
            }

            # Add new entry
            logs.append(log_entry)

            # Write back to file
            with open(self.log_file, 'w') as f:
                json.dump(logs, f, indent=2)

        except Exception as e:
            print(f"Error logging search: {e}")

    def get_recent_searches(self, limit: int = 100):
        try:
            # First ensure the file exists and has valid JSON
            self.ensure_log_file_exists()

            with open(self.log_file, 'r') as f:
                try:
                    logs = json.load(f)
                except json.JSONDecodeError:
                    return []
            return logs[-limit:]
        except Exception as e:
            print(f"Error getting recent searches: {e}")
            return []


# Create an instance of the logger
search_logger = SearchLogger()


# After your other global variables
special_cases_manager = SpecialCasesManager()

# Initialize some cases if you want (optional)
special_cases_manager.add_case(
    "pushpa 2",
    ["pushpa2", "pushpa-2", "pushpa2therule", "pushpa 2 the rule"],
    [
        {"url": "https://example4.com", "language": "Hindi"},
        {"url": "https://example5.com", "language": "Telugu"}
    ]
)

special_cases_manager.add_case(
    "venom",
    ["venom", "venom1", "venom2"],
    [
        {"url": "https://www.udlinks.com/3I1l", "language": "hindi"}
    ]
)




nest_asyncio.apply()

TELEGRAM_TOKEN = "7883754025:AAHUDU-_EM4QYome14k_28PQbPTWsl_9w6s"
TMDB_API_KEY = "c3b8704a4df65146c194940351efa9a2"
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
DELETE_TIMEOUT = 420  # 7 minutes in seconds
DISCLAIMER = "⚠️ This message will be deleted in 7 minutes"
HORROR_GENRE_ID = 27  # TMDB's genre ID for horror movies



USER_CONTEXT = {}

GENRE_IDS = {
    'horror': 27,
    'crime': 80,
    'romance': 10749
}


class TMDBAPIHandler:
    def __init__(self, api_key, base_url="https://api.themoviedb.org/3"):
        self.api_key = api_key
        self.base_url = base_url
        self.session = self._create_session()

    def _create_session(self):
        session = requests.Session()

        # Configure retry strategy
        retries = Retry(
            total=5,  # Total number of retries
            backoff_factor=0.5,  # Wait 0.5, 1, 2, 4, 8 seconds between retries
            status_forcelist=[500, 502, 503, 504, 408, 429]  # HTTP status codes to retry on
        )

        # Add retry adapter to session
        adapter = HTTPAdapter(max_retries=retries)
        session.mount('http://', adapter)
        session.mount('https://', adapter)

        return session

    def make_request(self, endpoint, params=None):
        if params is None:
            params = {}

        # Always include API key
        params['api_key'] = self.api_key

        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                response = self.session.get(
                    f"{self.base_url}{endpoint}",
                    params=params,
                    timeout=10  # 10 seconds timeout
                )
                response.raise_for_status()
                return response.json()

            except requests.exceptions.ConnectionError as e:
                if attempt == max_attempts - 1:
                    raise Exception("Unable to connect to TMDB API. Please check your internet connection.") from e
                time.sleep(2 ** attempt)  # Exponential backoff

            except requests.exceptions.Timeout as e:
                if attempt == max_attempts - 1:
                    raise Exception("TMDB API request timed out. Please try again later.") from e
                time.sleep(2 ** attempt)

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:  # Rate limit exceeded
                    retry_after = int(e.response.headers.get('Retry-After', 5))
                    time.sleep(retry_after)
                    continue
                raise Exception(f"TMDB API error: {e.response.status_code}") from e


LAST_ACTIVITY_FILE = "user_activity.pkl"
INACTIVITY_THRESHOLD = timedelta(hours=78)


class SearchStatistics:
    def __init__(self, log_file="search_logs.json", stats_file="stastics.txt"):
        self.log_file = log_file
        self.stats_file = stats_file
        self.search_logger = SearchLogger(log_file)
        # Ensure stastics file exists
        self.update_stastics_file()
        print(f"SearchStatistics initialized. Stats file: {stats_file}")

    def _load_searches(self):
        """Load searches from the log file"""
        try:
            with open(self.log_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def get_most_searched(self, days=None):
        """Get most searched queries within specified days"""
        searches = self._load_searches()
        if not searches:
            return []

        # Filter by date if days is specified
        if days:
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            searches = [s for s in searches if s['timestamp'][:10] >= cutoff_date]

        # Count search queries
        query_counts = {}
        for search in searches:
            query = search['search_query'].lower()
            query_counts[query] = query_counts.get(query, 0) + 1

        # Sort by count and return top 10
        return sorted(query_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    def get_user_search_history(self, limit=50):
        """Get recent user search history"""
        searches = self._load_searches()
        return searches[-limit:] if searches else []

    def update_stastics_file(self):  # Changed method name to match file name
        try:
            print(f"Updating stastics file at {datetime.now()}")

            # Check if log file exists and has data
            if not Path(self.log_file).exists():
                print(f"Log file {self.log_file} does not exist!")
                return

            # Load searches
            searches = self._load_searches()
            if not searches:
                print("No search data found in logs")
                stats_text = "No search data available yet.\nLast Updated: " + datetime.now().strftime(
                    '%Y-%m-%d %H:%M:%S')
            else:
                # Get statistics for different time periods
                all_time = self.get_most_searched()
                today = self.get_most_searched(days=1)
                week = self.get_most_searched(days=7)
                year = self.get_most_searched(days=365)
                user_history = self.get_user_search_history(limit=50)

                stats_text = self._format_stastics(all_time, today, week, year, user_history)  # Changed method name

            # Write to stastics file
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                f.write(stats_text)

            print(f"Stastics file updated successfully at {datetime.now()}")

            # Debug: Read and print file contents
            with open(self.stats_file, 'r', encoding='utf-8') as f:
                content = f.read()
            print(f"Stastics file size: {len(content)} bytes")

        except Exception as e:
            print(f"Error updating stastics file: {e}")
            import traceback
            traceback.print_exc()

    def _format_stastics(self, all_time, today, week, year, user_history):  # Changed method name
        stats_text = "Movie Search Stastics\n"  # Changed heading
        stats_text += "=" * 50 + "\n\n"

        # Add section for each time period
        sections = [
            ("All-Time Most Searched Movies:", all_time),
            ("Today's Most Searched Movies:", today),
            ("This Week's Most Searched Movies:", week),
            ("This Year's Most Searched Movies:", year)
        ]

        for title, data in sections:
            stats_text += f"{title}\n"
            if data:
                stats_text += "\n".join(f"{i + 1}. {movie} ({count} searches)"
                                      for i, (movie, count) in enumerate(data))
            else:
                stats_text += "No searches in this period"
            stats_text += "\n\n"

        # Add user history section
        stats_text += "Recent User Search History:\n"
        stats_text += "=" * 50 + "\n"
        if user_history:
            for search in user_history:
                stats_text += f"\nTime: {search['timestamp']}\n"
                stats_text += f"User: {search['user_name']} (ID: {search['user_id']})\n"
                stats_text += f"Search Type: {search['search_type']}\n"
                stats_text += f"Query: {search['search_query']}\n"
                stats_text += "-" * 30 + "\n"
        else:
            stats_text += "\nNo user search history available yet\n"

        stats_text += f"\nLast Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        return stats_text

# Modify the update_statistics_job to include error handling and logging
async def update_stastics_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        print(f"Starting stastics update job at {datetime.now()}")
        stats = SearchStatistics()
        stats.update_stastics_file()
        print(f"Completed stastics update job at {datetime.now()}")
    except Exception as e:
        print(f"Error in stastics update job: {e}")
        import traceback
        traceback.print_exc()

async def view_searches_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only allow yourself to see the searches
    if update.message.from_user.id == 6822829183:  # Replace with your Telegram ID
        recent_searches = search_logger.get_recent_searches(limit=10)  # Get last 10 searches

        message = "Recent Searches:\n\n"
        for search in recent_searches:
            message += f"👤 User: {search['user_name']}\n"
            message += f"🔍 Query: {search['search_query']}\n"
            message += f"⏰ Time: {search['timestamp']}\n"
            message += f"Type: {search['search_type']}\n\n"

        await update.message.reply_text(message)
    else:
        await update.message.reply_text("You don't have permission to use this command.")


# Add this to your command handlers

class UserActivityManager:
    def __init__(self):
        self.user_activity = {}
        self.load_activity()

    def load_activity(self):
        if Path(LAST_ACTIVITY_FILE).exists():
            try:
                with open(LAST_ACTIVITY_FILE, 'rb') as f:
                    self.user_activity = pickle.load(f)
            except Exception as e:
                print(f"Error loading user activity: {e}")
                self.user_activity = {}

    def save_activity(self):
        try:
            with open(LAST_ACTIVITY_FILE, 'wb') as f:
                pickle.dump(self.user_activity, f)
        except Exception as e:
            print(f"Error saving user activity: {e}")

    def update_user_activity(self, user_id: int, user_name: str):
        self.user_activity[user_id] = {
            'last_active': datetime.now(),
            'name': user_name
        }
        self.save_activity()

    def get_inactive_users(self):
        current_time = datetime.now()
        inactive_users = []

        for user_id, data in self.user_activity.items():
            if (current_time - data['last_active']) >= INACTIVITY_THRESHOLD:
                inactive_users.append({
                    'user_id': user_id,
                    'name': data['name'],
                    'last_active': data['last_active']
                })

        return inactive_users


# Create global instance
activity_manager = UserActivityManager()


# Modify the handle_user_message function to track activity
async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    await delete_message_later(context, update.message.chat_id, update.message.message_id)
    await handle_user_query(update, context)


# Add a new function to check for inactive users
async def check_inactive_users(context: ContextTypes.DEFAULT_TYPE):
    inactive_users = activity_manager.get_inactive_users()

    for user in inactive_users:
        try:
            message = f"Hey {user['name']} 👋,\n\nI am missing you dear! 💫\nIt's been a while since we last chatted. Come back and discover some amazing movies! 🎬"

            await context.bot.send_message(
                chat_id=user['user_id'],
                text=message,
                parse_mode='Markdown'
            )

            # Update the last activity to prevent spam
            activity_manager.update_user_activity(user['user_id'], user['name'])

        except Exception as e:
            print(f"Error sending reminder to user {user['user_id']}: {e}")

class MessageTracker:
    def __init__(self):
        self.messages: Dict[int, Dict[int, datetime]] = {}

    async def add_message(self, chat_id: int, message_id: int):
        if chat_id not in self.messages:
            self.messages[chat_id] = {}
        self.messages[chat_id][message_id] = datetime.now() + timedelta(seconds=DELETE_TIMEOUT)

    async def cleanup_messages(self, context: ContextTypes.DEFAULT_TYPE):
        current_time = datetime.now()
        for chat_id in list(self.messages.keys()):
            for message_id, expiry_time in list(self.messages[chat_id].items()):
                if current_time >= expiry_time:
                    try:
                        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                    except TelegramError:
                        pass  # Message might already be deleted
                    finally:
                        del self.messages[chat_id][message_id]
            if not self.messages[chat_id]:
                del self.messages[chat_id]

message_tracker = MessageTracker()

async def cleanup_job(context: ContextTypes.DEFAULT_TYPE):
    await message_tracker.cleanup_messages(context)

async def delete_message_later(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int):
    await message_tracker.add_message(chat_id, message_id)

async def send_with_warning(message, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None, parse_mode=None):
    try:
        if hasattr(message, 'reply_text'):
            sent_message = await message.reply_text(
                f"{text}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await message.edit_text(
                f"{text}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

        await delete_message_later(context, sent_message.chat_id, sent_message.message_id)
        return sent_message
    except TelegramError as e:
        print(f"Error sending message: {e}")
        return None

async def send_photo_with_warning(message, context: ContextTypes.DEFAULT_TYPE, photo: str, caption: str, reply_markup=None, parse_mode=None):
    try:
        if hasattr(message, 'reply_photo'):
            sent_message = await message.reply_photo(
                photo=photo,
                caption=f"{caption}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await context.bot.send_photo(
                chat_id=message.chat_id,
                photo=photo,
                caption=f"{caption}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

        await delete_message_later(context, sent_message.chat_id, sent_message.message_id)
        return sent_message
    except TelegramError as e:
        print(f"Error sending photo: {e}")
        return None


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    keyboard = [
        [InlineKeyboardButton("  DOWNLOAD MOVIES", callback_data='search_movies')],
        [
            InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
            InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
            InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
        ],
        [InlineKeyboardButton("📈 Popular Movies", callback_data='popular'),
         InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
        [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
        [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_with_warning(
        update.message,
        context,
        f"👋 Hello {user_name}! Welcome to @movieshuba11_bot!\n\nClick on /start to restart or type",
        reply_markup=reply_markup
    )

async def show_start_menu(message, context: ContextTypes.DEFAULT_TYPE):
    # Get user's name from the callback query
    user_name = message._effective_user.first_name if hasattr(message, '_effective_user') else "there"
    keyboard = [
        [InlineKeyboardButton(" Download movies", callback_data='search_movies')],
        [
            InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
            InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
            InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
        ],
        [InlineKeyboardButton("📈 Popular Movies", callback_data='popular')],
        [InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
        [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
        [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_with_warning(
        message,
        context,
        f"👋 Hello {user_name}! Welcome to moviieshubb_bot!\n\nClick on /start to restart or type",
        reply_markup=reply_markup
    )



async def get_random_movies_by_genre(message, context: ContextTypes.DEFAULT_TYPE, genre_id=None):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "sort_by": "popularity.desc",
            "page": 1
        }

        if genre_id:
            params["with_genres"] = genre_id

        response = requests.get(url, params=params)
        response.raise_for_status()
        total_pages = min(response.json().get("total_pages", 1), 500)

        random_page = random.randint(1, total_pages)
        params["page"] = random_page

        response = requests.get(url, params=params)
        response.raise_for_status()

        all_movies = response.json().get("results", [])
        random_movies = random.sample(all_movies, min(5, len(all_movies)))

        response_text = "🎲 Random Movie Suggestions:\n\n"
        keyboard = []
        for i, movie in enumerate(random_movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"
            keyboard.append([InlineKeyboardButton(f"🔍 Search {movie['title']}", callback_data=f'search_specific_{movie["id"]}')])

        keyboard.extend([
            [
                InlineKeyboardButton("👻 Horror", callback_data='random_horror'),
                InlineKeyboardButton("🔪 Crime", callback_data='random_crime'),
                InlineKeyboardButton("💝 Romance", callback_data='random_romance')
            ],
            [InlineKeyboardButton("🎲 More Random", callback_data='random_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching random movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='random_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                                "Sorry, couldn't fetch random movies right now.",
                                reply_markup=reply_markup)


async def get_popular_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/movie/popular"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "🎬 Currently Popular Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching popular movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='popular')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch popular movies right now.",
                              reply_markup=reply_markup)

async def get_horror_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "with_genres": HORROR_GENRE_ID,
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "👻 Popular Horror Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton("👻 More Horror Movies", callback_data='horror_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching horror movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='horror_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch horror movies right now.",
                              reply_markup=reply_markup)

async def get_bollywood_popular_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "region": "IN",
            "with_original_language": "hi",
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "🎬  Bollywood Popular Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching Bollywood movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='bollywood_popular')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch Bollywood movies right now.",
                              reply_markup=reply_markup)


async def search_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    special_case, special_links = special_cases_manager.is_special_case(query)
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Log the search
    search_logger.log_search(user_id, user_name, "movie", query)
    try:
        tmdb_handler = TMDBAPIHandler(TMDB_API_KEY)

        # Search for movie
        results = tmdb_handler.make_request(
            "/search/movie",
            params={"query": query, "language": "en-US"}
        ).get("results", [])

        if results:
            movie = results[0]
            movie_id = movie["id"]

            # Get movie details
            movie_details = tmdb_handler.make_request(f"/movie/{movie_id}")
            providers = tmdb_handler.make_request(f"/movie/{movie_id}/watch/providers").get("results", {}).get("US",
                                                                                                               {}).get(
                "flatrate", [])

        search_url = f"{TMDB_BASE_URL}/search/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        if results:
            movie = results[0]
            movie_id = movie["id"]

            details_url = f"{TMDB_BASE_URL}/movie/{movie_id}"
            watch_providers_url = f"{TMDB_BASE_URL}/movie/{movie_id}/watch/providers"

            details_response = requests.get(details_url, params={"api_key": TMDB_API_KEY})
            providers_response = requests.get(watch_providers_url, params={"api_key": TMDB_API_KEY})

            movie_details = details_response.json()
            providers = providers_response.json().get("results", {}).get("US", {}).get("flatrate", [])

            keyboard = [
                [InlineKeyboardButton(" Search Another Movie", callback_data='search_movies')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            response_text = (
                f"*{movie_details['title']}* ({movie_details.get('release_date', '')[:4]})\n\n"
                f"Plot: {movie_details.get('overview', 'No plot available')}\n\n"
            )

            if providers:
                response_text += "Available on: " + ", ".join(p["provider_name"] for p in providers) + "\n\n"
            else:
                response_text += "Streaming information not available\n\n"

            if special_case and special_links:
                response_text += "Download Links:\n"
                for link in special_links:
                    lang_text = f" ({link['language']})" if link.get('language') else ""
                    response_text += f"• {link['url']}{lang_text}\n"
            else:
                response_text += "download link comming soon msg @balaram129"

            if movie_details.get("poster_path"):
                poster_url = f"{TMDB_IMAGE_BASE_URL}{movie_details['poster_path']}"
                await send_photo_with_warning(update.message, context, photo=poster_url, caption=response_text, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                await send_with_warning(update.message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            keyboard = [
                [InlineKeyboardButton(" Try Again", callback_data='search_movies')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(update.message, context, "No movies found matching your search.", reply_markup=reply_markup)
    except Exception as e:
        print(f"Error in movie search: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(update.message, context,
                              "Sorry, there was an error processing your request. Please try again.",
                              reply_markup=reply_markup)

async def search_by_actor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Log the search
    search_logger.log_search(user_id, user_name, "actor", query)
    try:
        search_url = f"{TMDB_BASE_URL}/search/person"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        if results:
            actor = results[0]
            actor_id = actor["id"]

            actor_details_url = f"{TMDB_BASE_URL}/person/{actor_id}"
            movies_url = f"{TMDB_BASE_URL}/person/{actor_id}/movie_credits"

            actor_details_response = requests.get(actor_details_url, params={"api_key": TMDB_API_KEY})
            movies_response = requests.get(movies_url, params={"api_key": TMDB_API_KEY})

            actor_details = actor_details_response.json()
            movies = movies_response.json().get("cast", [])

            movies_with_rating = [m for m in movies if m.get("vote_average", 0) > 0]
            sorted_movies = sorted(movies_with_rating, key=lambda x: x.get("vote_average", 0), reverse=True)

            popular_movies = [m for m in sorted_movies if m.get("vote_average", 0) >= 7][:4]
            unpopular_movies = [m for m in sorted_movies if m.get("vote_average", 0) < 7][:4]

            response_text = f"🎭 {actor['name']}\n"
            if actor_details.get("birthday"):
                response_text += f"Birthday: {actor_details['birthday']}\n"
            if actor_details.get("place_of_birth"):
                response_text += f"Birthplace: {actor_details['place_of_birth']}\n"

            response_text += "\n📈 Highly Rated Movies:\n"
            for i, movie in enumerate(popular_movies, 1):
                response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
                response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"

            response_text += "\n📉 Other Notable Movies:\n"
            for i, movie in enumerate(unpopular_movies, 1):
                response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
                response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"

            keyboard = [
                [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
                [InlineKeyboardButton(" Search Another Actor", callback_data='search_actor')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            if actor.get("profile_path"):
                actor_image_url = f"{TMDB_IMAGE_BASE_URL}{actor['profile_path']}"
                await send_photo_with_warning(
                    update.message,
                    context,
                    photo=actor_image_url,
                    caption=response_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await send_with_warning(
                    update.message,
                    context,
                    response_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
        else:
            keyboard = [
                [InlineKeyboardButton(" Try Again", callback_data='search_actor')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                update.message,
                context,
                "No actor found matching your search.",
                reply_markup=reply_markup
            )
    except Exception as e:
        print(f"Error in actor search: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='search_actor')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(
            update.message,
            context,
            "Sorry, there was an error processing your request. Please try again.",
            reply_markup=reply_markup
        )
def is_special_case(query):
    query_lower = query.lower().strip()
    for key, case in special_cases_manager.items():
        if query_lower == key.lower() or query_lower in [v.lower() for v in case["variants"]]:
            return True, case["links"]
    return False, []

async def get_genre_movies(message, context: ContextTypes.DEFAULT_TYPE, genre_id: int, genre_name: str):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "with_genres": genre_id,
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = f"🎬 Popular {genre_name} Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching {genre_name} movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data=f'genre_{genre_name.lower()}')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              f"Sorry, couldn't fetch {genre_name} movies right now.",
                              reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_name = query.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    try:
        if query.data.startswith('search_specific_'):
            movie_id = query.data.split('_')[2]
            # Get movie details from TMDB
            url = f"{TMDB_BASE_URL}/movie/{movie_id}"
            response = requests.get(url, params={"api_key": TMDB_API_KEY})
            movie = response.json()

            # Create a message with movie details
            movie_text = f"{movie['title']} ({movie.get('release_date', '')[:4]})"

            # Send a temporary message to user's private chat
            class SimulatedMessage:
                def __init__(self, chat_id, text, from_user):
                    self.chat_id = chat_id
                    self.text = text
                    self.from_user = from_user

                def reply_text(self, *args, **kwargs):
                    return query.message.reply_text(*args, **kwargs)

                def reply_photo(self, *args, **kwargs):
                    return query.message.reply_photo(*args, **kwargs)

            # Create a proper message object
            simulated_message = SimulatedMessage(
                chat_id=query.message.chat_id,
                text=movie['title'],
                from_user=query.from_user
            )

            # Create a proper update object
            class SimulatedUpdate:
                def __init__(self, message):
                    self.message = message

            simulated_update = SimulatedUpdate(simulated_message)

            # Perform the search
            await search_movie(simulated_update, context)
            return
        if query.data == 'genre_horror':
            await get_genre_movies(query.message, context, GENRE_IDS['horror'], "Horror")
        elif query.data == 'genre_romance':
            await get_genre_movies(query.message, context, GENRE_IDS['romance'], "Romance")
        elif query.data == 'genre_crime':
            await get_genre_movies(query.message, context, GENRE_IDS['crime'], "Crime")
        elif query.data == 'random_movies':
            await get_random_movies_by_genre(query.message, context)
        if query.data == 'random_movies':
            await get_random_movies_by_genre(query.message, context)
        elif query.data == 'random_horror':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['horror'])
        elif query.data == 'random_crime':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['crime'])
        elif query.data == 'random_romance':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['romance'])
        elif query.data == 'horror_movies':
            await get_horror_movies(query.message, context)
        elif query.data == 'search_movies':
            USER_CONTEXT[query.message.chat_id] = 'movie'
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "🔍 Just type the name of any movie you want to search for!",
                reply_markup=reply_markup
            )
        elif query.data == 'search_actor':
            USER_CONTEXT[query.message.chat_id] = 'actor'
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "🎭 Just type the name of any actor to see their movies!",
                reply_markup=reply_markup
            )
        elif query.data == 'help':
            help_text = ("📖 How to use this bot:\n\n"
                        "1. Simply type any movie name\n"
                        "2. Or type any actor name to find their movies\n"
                        "3. I'll show you the details\n"
                        "4. Check out popular movies in both Hollywood and Bollywood\n"
                        "5. Try our random movie suggestions by genre!\n"
                        "Need more help? Just type /start to see the main menu again! or msg @balaram129")
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                help_text,
                reply_markup=reply_markup
            )
        elif query.data == 'popular':
            await get_popular_movies(query.message, context)
        elif query.data == 'bollywood_popular':
            await get_bollywood_popular_movies(query.message, context)
        elif query.data == 'start_menu':
            keyboard = [
                [InlineKeyboardButton("🔍 Download movies", callback_data='search_movies'),
                 InlineKeyboardButton("👻 Horror Movies", callback_data='horror_movies')],
                [
                    InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
                    InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
                    InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
                ],
                [InlineKeyboardButton("📈 Popular Movies", callback_data='popular')],
                [InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
                [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
                [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
                [InlineKeyboardButton("❓ Help", callback_data='help')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "👋 Welcome to moviieshubb_bot!\n\nClick on /start to restart or type",
                reply_markup=reply_markup
            )

    except Exception as e:
        print(f"Error in button callback: {e}")
        keyboard = [
            [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(
            query.message,
            context,
            "Sorry, there was an error processing your request. Please try again.",
            reply_markup=reply_markup
        )

async def handle_user_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_context = USER_CONTEXT.get(update.message.chat_id, "movie")
    if user_context == "actor":
        await search_by_actor(update, context)
    else:
        await search_movie(update, context)

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_message_later(context, update.message.chat_id, update.message.message_id)
    await handle_user_query(update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Exception while handling an update: {context.error}")
    if isinstance(context.error, Conflict):
        print("Bot instance already running. Exiting...")
        sys.exit(1)
    elif isinstance(context.error, NetworkError):
        print("Network error occurred. Waiting before retry...")
        await asyncio.sleep(1)
    else:
        print(f"Unexpected error: {context.error}")


def main():
    try:
        application = (
            Application.builder()
            .token(TELEGRAM_TOKEN)
            .build()
        )

        # Add existing handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CallbackQueryHandler(button_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))
        application.add_handler(CommandHandler("viewsearches", view_searches_command))

        # Add error handler
        application.add_error_handler(error_handler)

        # Set up the cleanup job to run every 10 seconds
        job_queue = application.job_queue
        job_queue.run_repeating(cleanup_job, interval=10, first=0)

        # Add the inactive user check job (runs every 6 hours)
        job_queue.run_repeating(check_inactive_users, interval=21600, first=21600)

        # Update stastics more frequently (every 5 minutes)
        job_queue.run_repeating(update_stastics_job, interval=300, first=0)

        # Initial statistics update
        print("Performing initial statistics update...")
        stats = SearchStatistics()
        stats.update_stastics_file()
        print("Initial statistics update completed")

        # Start the bot
        print("Starting bot...")
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

    except Exception as e:
        print(f"Error starting bot: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

# Test the logger
logger = SearchLogger()
logger.log_search(123456, "TestUser", "movie", "Avatar")

# Check recent searches
recent = logger.get_recent_searches()
print("Recent searches:", recent)import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import Conflict, NetworkError, TelegramError
import nest_asyncio
import sys
import random
from typing import Optional, Dict
from datetime import datetime, timedelta
import pickle
from special_cases_managerss import SpecialCasesManager
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import json
from datetime import datetime
from pathlib import Path


class SearchLogger:
    def __init__(self, log_file="search_logs.json"):
        self.log_file = log_file
        self.ensure_log_file_exists()

    def ensure_log_file_exists(self):
        # Create the file with an empty list if it doesn't exist or is empty
        if not Path(self.log_file).exists() or Path(self.log_file).stat().st_size == 0:
            with open(self.log_file, 'w') as f:
                json.dump([], f)

    def log_search(self, user_id: int, user_name: str, search_type: str, search_query: str):
        try:
            # First ensure the file exists and has valid JSON
            self.ensure_log_file_exists()

            # Read existing logs
            try:
                with open(self.log_file, 'r') as f:
                    logs = json.load(f)
            except json.JSONDecodeError:
                # If there's an error reading the JSON, start with an empty list
                logs = []

            # Create new log entry
            log_entry = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "user_id": user_id,
                "user_name": user_name,
                "search_type": search_type,
                "search_query": search_query
            }

            # Add new entry
            logs.append(log_entry)

            # Write back to file
            with open(self.log_file, 'w') as f:
                json.dump(logs, f, indent=2)

        except Exception as e:
            print(f"Error logging search: {e}")

    def get_recent_searches(self, limit: int = 100):
        try:
            # First ensure the file exists and has valid JSON
            self.ensure_log_file_exists()

            with open(self.log_file, 'r') as f:
                try:
                    logs = json.load(f)
                except json.JSONDecodeError:
                    return []
            return logs[-limit:]
        except Exception as e:
            print(f"Error getting recent searches: {e}")
            return []


# Create an instance of the logger
search_logger = SearchLogger()


# After your other global variables
special_cases_manager = SpecialCasesManager()

# Initialize some cases if you want (optional)
special_cases_manager.add_case(
    "pushpa 2",
    ["pushpa2", "pushpa-2", "pushpa2therule", "pushpa 2 the rule"],
    [
        {"url": "https://example4.com", "language": "Hindi"},
        {"url": "https://example5.com", "language": "Telugu"}
    ]
)

special_cases_manager.add_case(
    "venom",
    ["venom", "venom1", "venom2"],
    [
        {"url": "https://www.udlinks.com/3I1l", "language": "hindi"}
    ]
)




nest_asyncio.apply()

TELEGRAM_TOKEN = "7883754025:AAHUDU-_EM4QYome14k_28PQbPTWsl_9w6s"
TMDB_API_KEY = "c3b8704a4df65146c194940351efa9a2"
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
DELETE_TIMEOUT = 420  # 7 minutes in seconds
DISCLAIMER = "⚠️ This message will be deleted in 7 minutes"
HORROR_GENRE_ID = 27  # TMDB's genre ID for horror movies



USER_CONTEXT = {}

GENRE_IDS = {
    'horror': 27,
    'crime': 80,
    'romance': 10749
}


class TMDBAPIHandler:
    def __init__(self, api_key, base_url="https://api.themoviedb.org/3"):
        self.api_key = api_key
        self.base_url = base_url
        self.session = self._create_session()

    def _create_session(self):
        session = requests.Session()

        # Configure retry strategy
        retries = Retry(
            total=5,  # Total number of retries
            backoff_factor=0.5,  # Wait 0.5, 1, 2, 4, 8 seconds between retries
            status_forcelist=[500, 502, 503, 504, 408, 429]  # HTTP status codes to retry on
        )

        # Add retry adapter to session
        adapter = HTTPAdapter(max_retries=retries)
        session.mount('http://', adapter)
        session.mount('https://', adapter)

        return session

    def make_request(self, endpoint, params=None):
        if params is None:
            params = {}

        # Always include API key
        params['api_key'] = self.api_key

        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                response = self.session.get(
                    f"{self.base_url}{endpoint}",
                    params=params,
                    timeout=10  # 10 seconds timeout
                )
                response.raise_for_status()
                return response.json()

            except requests.exceptions.ConnectionError as e:
                if attempt == max_attempts - 1:
                    raise Exception("Unable to connect to TMDB API. Please check your internet connection.") from e
                time.sleep(2 ** attempt)  # Exponential backoff

            except requests.exceptions.Timeout as e:
                if attempt == max_attempts - 1:
                    raise Exception("TMDB API request timed out. Please try again later.") from e
                time.sleep(2 ** attempt)

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:  # Rate limit exceeded
                    retry_after = int(e.response.headers.get('Retry-After', 5))
                    time.sleep(retry_after)
                    continue
                raise Exception(f"TMDB API error: {e.response.status_code}") from e


LAST_ACTIVITY_FILE = "user_activity.pkl"
INACTIVITY_THRESHOLD = timedelta(hours=78)


class SearchStatistics:
    def __init__(self, log_file="search_logs.json", stats_file="stastics.txt"):
        self.log_file = log_file
        self.stats_file = stats_file
        self.search_logger = SearchLogger(log_file)
        # Ensure stastics file exists
        self.update_stastics_file()
        print(f"SearchStatistics initialized. Stats file: {stats_file}")

    def _load_searches(self):
        """Load searches from the log file"""
        try:
            with open(self.log_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def get_most_searched(self, days=None):
        """Get most searched queries within specified days"""
        searches = self._load_searches()
        if not searches:
            return []

        # Filter by date if days is specified
        if days:
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            searches = [s for s in searches if s['timestamp'][:10] >= cutoff_date]

        # Count search queries
        query_counts = {}
        for search in searches:
            query = search['search_query'].lower()
            query_counts[query] = query_counts.get(query, 0) + 1

        # Sort by count and return top 10
        return sorted(query_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    def get_user_search_history(self, limit=50):
        """Get recent user search history"""
        searches = self._load_searches()
        return searches[-limit:] if searches else []

    def update_stastics_file(self):  # Changed method name to match file name
        try:
            print(f"Updating stastics file at {datetime.now()}")

            # Check if log file exists and has data
            if not Path(self.log_file).exists():
                print(f"Log file {self.log_file} does not exist!")
                return

            # Load searches
            searches = self._load_searches()
            if not searches:
                print("No search data found in logs")
                stats_text = "No search data available yet.\nLast Updated: " + datetime.now().strftime(
                    '%Y-%m-%d %H:%M:%S')
            else:
                # Get statistics for different time periods
                all_time = self.get_most_searched()
                today = self.get_most_searched(days=1)
                week = self.get_most_searched(days=7)
                year = self.get_most_searched(days=365)
                user_history = self.get_user_search_history(limit=50)

                stats_text = self._format_stastics(all_time, today, week, year, user_history)  # Changed method name

            # Write to stastics file
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                f.write(stats_text)

            print(f"Stastics file updated successfully at {datetime.now()}")

            # Debug: Read and print file contents
            with open(self.stats_file, 'r', encoding='utf-8') as f:
                content = f.read()
            print(f"Stastics file size: {len(content)} bytes")

        except Exception as e:
            print(f"Error updating stastics file: {e}")
            import traceback
            traceback.print_exc()

    def _format_stastics(self, all_time, today, week, year, user_history):  # Changed method name
        stats_text = "Movie Search Stastics\n"  # Changed heading
        stats_text += "=" * 50 + "\n\n"

        # Add section for each time period
        sections = [
            ("All-Time Most Searched Movies:", all_time),
            ("Today's Most Searched Movies:", today),
            ("This Week's Most Searched Movies:", week),
            ("This Year's Most Searched Movies:", year)
        ]

        for title, data in sections:
            stats_text += f"{title}\n"
            if data:
                stats_text += "\n".join(f"{i + 1}. {movie} ({count} searches)"
                                      for i, (movie, count) in enumerate(data))
            else:
                stats_text += "No searches in this period"
            stats_text += "\n\n"

        # Add user history section
        stats_text += "Recent User Search History:\n"
        stats_text += "=" * 50 + "\n"
        if user_history:
            for search in user_history:
                stats_text += f"\nTime: {search['timestamp']}\n"
                stats_text += f"User: {search['user_name']} (ID: {search['user_id']})\n"
                stats_text += f"Search Type: {search['search_type']}\n"
                stats_text += f"Query: {search['search_query']}\n"
                stats_text += "-" * 30 + "\n"
        else:
            stats_text += "\nNo user search history available yet\n"

        stats_text += f"\nLast Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        return stats_text

# Modify the update_statistics_job to include error handling and logging
async def update_stastics_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        print(f"Starting stastics update job at {datetime.now()}")
        stats = SearchStatistics()
        stats.update_stastics_file()
        print(f"Completed stastics update job at {datetime.now()}")
    except Exception as e:
        print(f"Error in stastics update job: {e}")
        import traceback
        traceback.print_exc()

async def view_searches_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only allow yourself to see the searches
    if update.message.from_user.id == 6822829183:  # Replace with your Telegram ID
        recent_searches = search_logger.get_recent_searches(limit=10)  # Get last 10 searches

        message = "Recent Searches:\n\n"
        for search in recent_searches:
            message += f"👤 User: {search['user_name']}\n"
            message += f"🔍 Query: {search['search_query']}\n"
            message += f"⏰ Time: {search['timestamp']}\n"
            message += f"Type: {search['search_type']}\n\n"

        await update.message.reply_text(message)
    else:
        await update.message.reply_text("You don't have permission to use this command.")


# Add this to your command handlers

class UserActivityManager:
    def __init__(self):
        self.user_activity = {}
        self.load_activity()

    def load_activity(self):
        if Path(LAST_ACTIVITY_FILE).exists():
            try:
                with open(LAST_ACTIVITY_FILE, 'rb') as f:
                    self.user_activity = pickle.load(f)
            except Exception as e:
                print(f"Error loading user activity: {e}")
                self.user_activity = {}

    def save_activity(self):
        try:
            with open(LAST_ACTIVITY_FILE, 'wb') as f:
                pickle.dump(self.user_activity, f)
        except Exception as e:
            print(f"Error saving user activity: {e}")

    def update_user_activity(self, user_id: int, user_name: str):
        self.user_activity[user_id] = {
            'last_active': datetime.now(),
            'name': user_name
        }
        self.save_activity()

    def get_inactive_users(self):
        current_time = datetime.now()
        inactive_users = []

        for user_id, data in self.user_activity.items():
            if (current_time - data['last_active']) >= INACTIVITY_THRESHOLD:
                inactive_users.append({
                    'user_id': user_id,
                    'name': data['name'],
                    'last_active': data['last_active']
                })

        return inactive_users


# Create global instance
activity_manager = UserActivityManager()


# Modify the handle_user_message function to track activity
async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    await delete_message_later(context, update.message.chat_id, update.message.message_id)
    await handle_user_query(update, context)


# Add a new function to check for inactive users
async def check_inactive_users(context: ContextTypes.DEFAULT_TYPE):
    inactive_users = activity_manager.get_inactive_users()

    for user in inactive_users:
        try:
            message = f"Hey {user['name']} 👋,\n\nI am missing you dear! 💫\nIt's been a while since we last chatted. Come back and discover some amazing movies! 🎬"

            await context.bot.send_message(
                chat_id=user['user_id'],
                text=message,
                parse_mode='Markdown'
            )

            # Update the last activity to prevent spam
            activity_manager.update_user_activity(user['user_id'], user['name'])

        except Exception as e:
            print(f"Error sending reminder to user {user['user_id']}: {e}")

class MessageTracker:
    def __init__(self):
        self.messages: Dict[int, Dict[int, datetime]] = {}

    async def add_message(self, chat_id: int, message_id: int):
        if chat_id not in self.messages:
            self.messages[chat_id] = {}
        self.messages[chat_id][message_id] = datetime.now() + timedelta(seconds=DELETE_TIMEOUT)

    async def cleanup_messages(self, context: ContextTypes.DEFAULT_TYPE):
        current_time = datetime.now()
        for chat_id in list(self.messages.keys()):
            for message_id, expiry_time in list(self.messages[chat_id].items()):
                if current_time >= expiry_time:
                    try:
                        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                    except TelegramError:
                        pass  # Message might already be deleted
                    finally:
                        del self.messages[chat_id][message_id]
            if not self.messages[chat_id]:
                del self.messages[chat_id]

message_tracker = MessageTracker()

async def cleanup_job(context: ContextTypes.DEFAULT_TYPE):
    await message_tracker.cleanup_messages(context)

async def delete_message_later(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int):
    await message_tracker.add_message(chat_id, message_id)

async def send_with_warning(message, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None, parse_mode=None):
    try:
        if hasattr(message, 'reply_text'):
            sent_message = await message.reply_text(
                f"{text}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await message.edit_text(
                f"{text}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

        await delete_message_later(context, sent_message.chat_id, sent_message.message_id)
        return sent_message
    except TelegramError as e:
        print(f"Error sending message: {e}")
        return None

async def send_photo_with_warning(message, context: ContextTypes.DEFAULT_TYPE, photo: str, caption: str, reply_markup=None, parse_mode=None):
    try:
        if hasattr(message, 'reply_photo'):
            sent_message = await message.reply_photo(
                photo=photo,
                caption=f"{caption}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await context.bot.send_photo(
                chat_id=message.chat_id,
                photo=photo,
                caption=f"{caption}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

        await delete_message_later(context, sent_message.chat_id, sent_message.message_id)
        return sent_message
    except TelegramError as e:
        print(f"Error sending photo: {e}")
        return None


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    keyboard = [
        [InlineKeyboardButton("  DOWNLOAD MOVIES", callback_data='search_movies')],
        [
            InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
            InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
            InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
        ],
        [InlineKeyboardButton("📈 Popular Movies", callback_data='popular'),
         InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
        [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
        [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_with_warning(
        update.message,
        context,
        f"👋 Hello {user_name}! Welcome to @movieshuba11_bot!\n\nClick on /start to restart or type",
        reply_markup=reply_markup
    )

async def show_start_menu(message, context: ContextTypes.DEFAULT_TYPE):
    # Get user's name from the callback query
    user_name = message._effective_user.first_name if hasattr(message, '_effective_user') else "there"
    keyboard = [
        [InlineKeyboardButton(" Download movies", callback_data='search_movies')],
        [
            InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
            InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
            InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
        ],
        [InlineKeyboardButton("📈 Popular Movies", callback_data='popular')],
        [InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
        [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
        [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_with_warning(
        message,
        context,
        f"👋 Hello {user_name}! Welcome to moviieshubb_bot!\n\nClick on /start to restart or type",
        reply_markup=reply_markup
    )



async def get_random_movies_by_genre(message, context: ContextTypes.DEFAULT_TYPE, genre_id=None):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "sort_by": "popularity.desc",
            "page": 1
        }

        if genre_id:
            params["with_genres"] = genre_id

        response = requests.get(url, params=params)
        response.raise_for_status()
        total_pages = min(response.json().get("total_pages", 1), 500)

        random_page = random.randint(1, total_pages)
        params["page"] = random_page

        response = requests.get(url, params=params)
        response.raise_for_status()

        all_movies = response.json().get("results", [])
        random_movies = random.sample(all_movies, min(5, len(all_movies)))

        response_text = "🎲 Random Movie Suggestions:\n\n"
        keyboard = []
        for i, movie in enumerate(random_movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"
            keyboard.append([InlineKeyboardButton(f"🔍 Search {movie['title']}", callback_data=f'search_specific_{movie["id"]}')])

        keyboard.extend([
            [
                InlineKeyboardButton("👻 Horror", callback_data='random_horror'),
                InlineKeyboardButton("🔪 Crime", callback_data='random_crime'),
                InlineKeyboardButton("💝 Romance", callback_data='random_romance')
            ],
            [InlineKeyboardButton("🎲 More Random", callback_data='random_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching random movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='random_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                                "Sorry, couldn't fetch random movies right now.",
                                reply_markup=reply_markup)


async def get_popular_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/movie/popular"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "🎬 Currently Popular Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching popular movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='popular')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch popular movies right now.",
                              reply_markup=reply_markup)

async def get_horror_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "with_genres": HORROR_GENRE_ID,
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "👻 Popular Horror Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton("👻 More Horror Movies", callback_data='horror_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching horror movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='horror_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch horror movies right now.",
                              reply_markup=reply_markup)

async def get_bollywood_popular_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "region": "IN",
            "with_original_language": "hi",
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "🎬  Bollywood Popular Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching Bollywood movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='bollywood_popular')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch Bollywood movies right now.",
                              reply_markup=reply_markup)


async def search_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    special_case, special_links = special_cases_manager.is_special_case(query)
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Log the search
    search_logger.log_search(user_id, user_name, "movie", query)
    try:
        tmdb_handler = TMDBAPIHandler(TMDB_API_KEY)

        # Search for movie
        results = tmdb_handler.make_request(
            "/search/movie",
            params={"query": query, "language": "en-US"}
        ).get("results", [])

        if results:
            movie = results[0]
            movie_id = movie["id"]

            # Get movie details
            movie_details = tmdb_handler.make_request(f"/movie/{movie_id}")
            providers = tmdb_handler.make_request(f"/movie/{movie_id}/watch/providers").get("results", {}).get("US",
                                                                                                               {}).get(
                "flatrate", [])

        search_url = f"{TMDB_BASE_URL}/search/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        if results:
            movie = results[0]
            movie_id = movie["id"]

            details_url = f"{TMDB_BASE_URL}/movie/{movie_id}"
            watch_providers_url = f"{TMDB_BASE_URL}/movie/{movie_id}/watch/providers"

            details_response = requests.get(details_url, params={"api_key": TMDB_API_KEY})
            providers_response = requests.get(watch_providers_url, params={"api_key": TMDB_API_KEY})

            movie_details = details_response.json()
            providers = providers_response.json().get("results", {}).get("US", {}).get("flatrate", [])

            keyboard = [
                [InlineKeyboardButton(" Search Another Movie", callback_data='search_movies')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            response_text = (
                f"*{movie_details['title']}* ({movie_details.get('release_date', '')[:4]})\n\n"
                f"Plot: {movie_details.get('overview', 'No plot available')}\n\n"
            )

            if providers:
                response_text += "Available on: " + ", ".join(p["provider_name"] for p in providers) + "\n\n"
            else:
                response_text += "Streaming information not available\n\n"

            if special_case and special_links:
                response_text += "Download Links:\n"
                for link in special_links:
                    lang_text = f" ({link['language']})" if link.get('language') else ""
                    response_text += f"• {link['url']}{lang_text}\n"
            else:
                response_text += "download link comming soon msg @balaram129"

            if movie_details.get("poster_path"):
                poster_url = f"{TMDB_IMAGE_BASE_URL}{movie_details['poster_path']}"
                await send_photo_with_warning(update.message, context, photo=poster_url, caption=response_text, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                await send_with_warning(update.message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            keyboard = [
                [InlineKeyboardButton(" Try Again", callback_data='search_movies')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(update.message, context, "No movies found matching your search.", reply_markup=reply_markup)
    except Exception as e:
        print(f"Error in movie search: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(update.message, context,
                              "Sorry, there was an error processing your request. Please try again.",
                              reply_markup=reply_markup)

async def search_by_actor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Log the search
    search_logger.log_search(user_id, user_name, "actor", query)
    try:
        search_url = f"{TMDB_BASE_URL}/search/person"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        if results:
            actor = results[0]
            actor_id = actor["id"]

            actor_details_url = f"{TMDB_BASE_URL}/person/{actor_id}"
            movies_url = f"{TMDB_BASE_URL}/person/{actor_id}/movie_credits"

            actor_details_response = requests.get(actor_details_url, params={"api_key": TMDB_API_KEY})
            movies_response = requests.get(movies_url, params={"api_key": TMDB_API_KEY})

            actor_details = actor_details_response.json()
            movies = movies_response.json().get("cast", [])

            movies_with_rating = [m for m in movies if m.get("vote_average", 0) > 0]
            sorted_movies = sorted(movies_with_rating, key=lambda x: x.get("vote_average", 0), reverse=True)

            popular_movies = [m for m in sorted_movies if m.get("vote_average", 0) >= 7][:4]
            unpopular_movies = [m for m in sorted_movies if m.get("vote_average", 0) < 7][:4]

            response_text = f"🎭 {actor['name']}\n"
            if actor_details.get("birthday"):
                response_text += f"Birthday: {actor_details['birthday']}\n"
            if actor_details.get("place_of_birth"):
                response_text += f"Birthplace: {actor_details['place_of_birth']}\n"

            response_text += "\n📈 Highly Rated Movies:\n"
            for i, movie in enumerate(popular_movies, 1):
                response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
                response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"

            response_text += "\n📉 Other Notable Movies:\n"
            for i, movie in enumerate(unpopular_movies, 1):
                response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
                response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"

            keyboard = [
                [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
                [InlineKeyboardButton(" Search Another Actor", callback_data='search_actor')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            if actor.get("profile_path"):
                actor_image_url = f"{TMDB_IMAGE_BASE_URL}{actor['profile_path']}"
                await send_photo_with_warning(
                    update.message,
                    context,
                    photo=actor_image_url,
                    caption=response_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await send_with_warning(
                    update.message,
                    context,
                    response_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
        else:
            keyboard = [
                [InlineKeyboardButton(" Try Again", callback_data='search_actor')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                update.message,
                context,
                "No actor found matching your search.",
                reply_markup=reply_markup
            )
    except Exception as e:
        print(f"Error in actor search: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='search_actor')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(
            update.message,
            context,
            "Sorry, there was an error processing your request. Please try again.",
            reply_markup=reply_markup
        )
def is_special_case(query):
    query_lower = query.lower().strip()
    for key, case in special_cases_manager.items():
        if query_lower == key.lower() or query_lower in [v.lower() for v in case["variants"]]:
            return True, case["links"]
    return False, []

async def get_genre_movies(message, context: ContextTypes.DEFAULT_TYPE, genre_id: int, genre_name: str):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "with_genres": genre_id,
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = f"🎬 Popular {genre_name} Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching {genre_name} movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data=f'genre_{genre_name.lower()}')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              f"Sorry, couldn't fetch {genre_name} movies right now.",
                              reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_name = query.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    try:
        if query.data.startswith('search_specific_'):
            movie_id = query.data.split('_')[2]
            # Get movie details from TMDB
            url = f"{TMDB_BASE_URL}/movie/{movie_id}"
            response = requests.get(url, params={"api_key": TMDB_API_KEY})
            movie = response.json()

            # Create a message with movie details
            movie_text = f"{movie['title']} ({movie.get('release_date', '')[:4]})"

            # Send a temporary message to user's private chat
            class SimulatedMessage:
                def __init__(self, chat_id, text, from_user):
                    self.chat_id = chat_id
                    self.text = text
                    self.from_user = from_user

                def reply_text(self, *args, **kwargs):
                    return query.message.reply_text(*args, **kwargs)

                def reply_photo(self, *args, **kwargs):
                    return query.message.reply_photo(*args, **kwargs)

            # Create a proper message object
            simulated_message = SimulatedMessage(
                chat_id=query.message.chat_id,
                text=movie['title'],
                from_user=query.from_user
            )

            # Create a proper update object
            class SimulatedUpdate:
                def __init__(self, message):
                    self.message = message

            simulated_update = SimulatedUpdate(simulated_message)

            # Perform the search
            await search_movie(simulated_update, context)
            return
        if query.data == 'genre_horror':
            await get_genre_movies(query.message, context, GENRE_IDS['horror'], "Horror")
        elif query.data == 'genre_romance':
            await get_genre_movies(query.message, context, GENRE_IDS['romance'], "Romance")
        elif query.data == 'genre_crime':
            await get_genre_movies(query.message, context, GENRE_IDS['crime'], "Crime")
        elif query.data == 'random_movies':
            await get_random_movies_by_genre(query.message, context)
        if query.data == 'random_movies':
            await get_random_movies_by_genre(query.message, context)
        elif query.data == 'random_horror':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['horror'])
        elif query.data == 'random_crime':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['crime'])
        elif query.data == 'random_romance':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['romance'])
        elif query.data == 'horror_movies':
            await get_horror_movies(query.message, context)
        elif query.data == 'search_movies':
            USER_CONTEXT[query.message.chat_id] = 'movie'
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "🔍 Just type the name of any movie you want to search for!",
                reply_markup=reply_markup
            )
        elif query.data == 'search_actor':
            USER_CONTEXT[query.message.chat_id] = 'actor'
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "🎭 Just type the name of any actor to see their movies!",
                reply_markup=reply_markup
            )
        elif query.data == 'help':
            help_text = ("📖 How to use this bot:\n\n"
                        "1. Simply type any movie name\n"
                        "2. Or type any actor name to find their movies\n"
                        "3. I'll show you the details\n"
                        "4. Check out popular movies in both Hollywood and Bollywood\n"
                        "5. Try our random movie suggestions by genre!\n"
                        "Need more help? Just type /start to see the main menu again! or msg @balaram129")
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                help_text,
                reply_markup=reply_markup
            )
        elif query.data == 'popular':
            await get_popular_movies(query.message, context)
        elif query.data == 'bollywood_popular':
            await get_bollywood_popular_movies(query.message, context)
        elif query.data == 'start_menu':
            keyboard = [
                [InlineKeyboardButton("🔍 Download movies", callback_data='search_movies'),
                 InlineKeyboardButton("👻 Horror Movies", callback_data='horror_movies')],
                [
                    InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
                    InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
                    InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
                ],
                [InlineKeyboardButton("📈 Popular Movies", callback_data='popular')],
                [InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
                [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
                [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
                [InlineKeyboardButton("❓ Help", callback_data='help')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "👋 Welcome to moviieshubb_bot!\n\nClick on /start to restart or type",
                reply_markup=reply_markup
            )

    except Exception as e:
        print(f"Error in button callback: {e}")
        keyboard = [
            [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(
            query.message,
            context,
            "Sorry, there was an error processing your request. Please try again.",
            reply_markup=reply_markup
        )

async def handle_user_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_context = USER_CONTEXT.get(update.message.chat_id, "movie")
    if user_context == "actor":
        await search_by_actor(update, context)
    else:
        await search_movie(update, context)

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_message_later(context, update.message.chat_id, update.message.message_id)
    await handle_user_query(update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Exception while handling an update: {context.error}")
    if isinstance(context.error, Conflict):
        print("Bot instance already running. Exiting...")
        sys.exit(1)
    elif isinstance(context.error, NetworkError):
        print("Network error occurred. Waiting before retry...")
        await asyncio.sleep(1)
    else:
        print(f"Unexpected error: {context.error}")


def main():
    try:
        application = (
            Application.builder()
            .token(TELEGRAM_TOKEN)
            .build()
        )

        # Add existing handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CallbackQueryHandler(button_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))
        application.add_handler(CommandHandler("viewsearches", view_searches_command))

        # Add error handler
        application.add_error_handler(error_handler)

        # Set up the cleanup job to run every 10 seconds
        job_queue = application.job_queue
        job_queue.run_repeating(cleanup_job, interval=10, first=0)

        # Add the inactive user check job (runs every 6 hours)
        job_queue.run_repeating(check_inactive_users, interval=21600, first=21600)

        # Update stastics more frequently (every 5 minutes)
        job_queue.run_repeating(update_stastics_job, interval=300, first=0)

        # Initial statistics update
        print("Performing initial statistics update...")
        stats = SearchStatistics()
        stats.update_stastics_file()
        print("Initial statistics update completed")

        # Start the bot
        print("Starting bot...")
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

    except Exception as e:
        print(f"Error starting bot: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

# Test the logger
logger = SearchLogger()
logger.log_search(123456, "TestUser", "movie", "Avatar")

# Check recent searches
recent = logger.get_recent_searches()
print("Recent searches:", recent)import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import Conflict, NetworkError, TelegramError
import nest_asyncio
import sys
import random
from typing import Optional, Dict
from datetime import datetime, timedelta
import pickle
from special_cases_managerss import SpecialCasesManager
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import json
from datetime import datetime
from pathlib import Path


class SearchLogger:
    def __init__(self, log_file="search_logs.json"):
        self.log_file = log_file
        self.ensure_log_file_exists()

    def ensure_log_file_exists(self):
        # Create the file with an empty list if it doesn't exist or is empty
        if not Path(self.log_file).exists() or Path(self.log_file).stat().st_size == 0:
            with open(self.log_file, 'w') as f:
                json.dump([], f)

    def log_search(self, user_id: int, user_name: str, search_type: str, search_query: str):
        try:
            # First ensure the file exists and has valid JSON
            self.ensure_log_file_exists()

            # Read existing logs
            try:
                with open(self.log_file, 'r') as f:
                    logs = json.load(f)
            except json.JSONDecodeError:
                # If there's an error reading the JSON, start with an empty list
                logs = []

            # Create new log entry
            log_entry = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "user_id": user_id,
                "user_name": user_name,
                "search_type": search_type,
                "search_query": search_query
            }

            # Add new entry
            logs.append(log_entry)

            # Write back to file
            with open(self.log_file, 'w') as f:
                json.dump(logs, f, indent=2)

        except Exception as e:
            print(f"Error logging search: {e}")

    def get_recent_searches(self, limit: int = 100):
        try:
            # First ensure the file exists and has valid JSON
            self.ensure_log_file_exists()

            with open(self.log_file, 'r') as f:
                try:
                    logs = json.load(f)
                except json.JSONDecodeError:
                    return []
            return logs[-limit:]
        except Exception as e:
            print(f"Error getting recent searches: {e}")
            return []


# Create an instance of the logger
search_logger = SearchLogger()


# After your other global variables
special_cases_manager = SpecialCasesManager()

# Initialize some cases if you want (optional)
special_cases_manager.add_case(
    "pushpa 2",
    ["pushpa2", "pushpa-2", "pushpa2therule", "pushpa 2 the rule"],
    [
        {"url": "https://example4.com", "language": "Hindi"},
        {"url": "https://example5.com", "language": "Telugu"}
    ]
)

special_cases_manager.add_case(
    "venom",
    ["venom", "venom1", "venom2"],
    [
        {"url": "https://www.udlinks.com/3I1l", "language": "hindi"}
    ]
)




nest_asyncio.apply()

TELEGRAM_TOKEN = "7883754025:AAHUDU-_EM4QYome14k_28PQbPTWsl_9w6s"
TMDB_API_KEY = "c3b8704a4df65146c194940351efa9a2"
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
DELETE_TIMEOUT = 420  # 7 minutes in seconds
DISCLAIMER = "⚠️ This message will be deleted in 7 minutes"
HORROR_GENRE_ID = 27  # TMDB's genre ID for horror movies



USER_CONTEXT = {}

GENRE_IDS = {
    'horror': 27,
    'crime': 80,
    'romance': 10749
}


class TMDBAPIHandler:
    def __init__(self, api_key, base_url="https://api.themoviedb.org/3"):
        self.api_key = api_key
        self.base_url = base_url
        self.session = self._create_session()

    def _create_session(self):
        session = requests.Session()

        # Configure retry strategy
        retries = Retry(
            total=5,  # Total number of retries
            backoff_factor=0.5,  # Wait 0.5, 1, 2, 4, 8 seconds between retries
            status_forcelist=[500, 502, 503, 504, 408, 429]  # HTTP status codes to retry on
        )

        # Add retry adapter to session
        adapter = HTTPAdapter(max_retries=retries)
        session.mount('http://', adapter)
        session.mount('https://', adapter)

        return session

    def make_request(self, endpoint, params=None):
        if params is None:
            params = {}

        # Always include API key
        params['api_key'] = self.api_key

        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                response = self.session.get(
                    f"{self.base_url}{endpoint}",
                    params=params,
                    timeout=10  # 10 seconds timeout
                )
                response.raise_for_status()
                return response.json()

            except requests.exceptions.ConnectionError as e:
                if attempt == max_attempts - 1:
                    raise Exception("Unable to connect to TMDB API. Please check your internet connection.") from e
                time.sleep(2 ** attempt)  # Exponential backoff

            except requests.exceptions.Timeout as e:
                if attempt == max_attempts - 1:
                    raise Exception("TMDB API request timed out. Please try again later.") from e
                time.sleep(2 ** attempt)

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:  # Rate limit exceeded
                    retry_after = int(e.response.headers.get('Retry-After', 5))
                    time.sleep(retry_after)
                    continue
                raise Exception(f"TMDB API error: {e.response.status_code}") from e


LAST_ACTIVITY_FILE = "user_activity.pkl"
INACTIVITY_THRESHOLD = timedelta(hours=78)


class SearchStatistics:
    def __init__(self, log_file="search_logs.json", stats_file="stastics.txt"):
        self.log_file = log_file
        self.stats_file = stats_file
        self.search_logger = SearchLogger(log_file)
        # Ensure stastics file exists
        self.update_stastics_file()
        print(f"SearchStatistics initialized. Stats file: {stats_file}")

    def _load_searches(self):
        """Load searches from the log file"""
        try:
            with open(self.log_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def get_most_searched(self, days=None):
        """Get most searched queries within specified days"""
        searches = self._load_searches()
        if not searches:
            return []

        # Filter by date if days is specified
        if days:
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            searches = [s for s in searches if s['timestamp'][:10] >= cutoff_date]

        # Count search queries
        query_counts = {}
        for search in searches:
            query = search['search_query'].lower()
            query_counts[query] = query_counts.get(query, 0) + 1

        # Sort by count and return top 10
        return sorted(query_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    def get_user_search_history(self, limit=50):
        """Get recent user search history"""
        searches = self._load_searches()
        return searches[-limit:] if searches else []

    def update_stastics_file(self):  # Changed method name to match file name
        try:
            print(f"Updating stastics file at {datetime.now()}")

            # Check if log file exists and has data
            if not Path(self.log_file).exists():
                print(f"Log file {self.log_file} does not exist!")
                return

            # Load searches
            searches = self._load_searches()
            if not searches:
                print("No search data found in logs")
                stats_text = "No search data available yet.\nLast Updated: " + datetime.now().strftime(
                    '%Y-%m-%d %H:%M:%S')
            else:
                # Get statistics for different time periods
                all_time = self.get_most_searched()
                today = self.get_most_searched(days=1)
                week = self.get_most_searched(days=7)
                year = self.get_most_searched(days=365)
                user_history = self.get_user_search_history(limit=50)

                stats_text = self._format_stastics(all_time, today, week, year, user_history)  # Changed method name

            # Write to stastics file
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                f.write(stats_text)

            print(f"Stastics file updated successfully at {datetime.now()}")

            # Debug: Read and print file contents
            with open(self.stats_file, 'r', encoding='utf-8') as f:
                content = f.read()
            print(f"Stastics file size: {len(content)} bytes")

        except Exception as e:
            print(f"Error updating stastics file: {e}")
            import traceback
            traceback.print_exc()

    def _format_stastics(self, all_time, today, week, year, user_history):  # Changed method name
        stats_text = "Movie Search Stastics\n"  # Changed heading
        stats_text += "=" * 50 + "\n\n"

        # Add section for each time period
        sections = [
            ("All-Time Most Searched Movies:", all_time),
            ("Today's Most Searched Movies:", today),
            ("This Week's Most Searched Movies:", week),
            ("This Year's Most Searched Movies:", year)
        ]

        for title, data in sections:
            stats_text += f"{title}\n"
            if data:
                stats_text += "\n".join(f"{i + 1}. {movie} ({count} searches)"
                                      for i, (movie, count) in enumerate(data))
            else:
                stats_text += "No searches in this period"
            stats_text += "\n\n"

        # Add user history section
        stats_text += "Recent User Search History:\n"
        stats_text += "=" * 50 + "\n"
        if user_history:
            for search in user_history:
                stats_text += f"\nTime: {search['timestamp']}\n"
                stats_text += f"User: {search['user_name']} (ID: {search['user_id']})\n"
                stats_text += f"Search Type: {search['search_type']}\n"
                stats_text += f"Query: {search['search_query']}\n"
                stats_text += "-" * 30 + "\n"
        else:
            stats_text += "\nNo user search history available yet\n"

        stats_text += f"\nLast Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        return stats_text

# Modify the update_statistics_job to include error handling and logging
async def update_stastics_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        print(f"Starting stastics update job at {datetime.now()}")
        stats = SearchStatistics()
        stats.update_stastics_file()
        print(f"Completed stastics update job at {datetime.now()}")
    except Exception as e:
        print(f"Error in stastics update job: {e}")
        import traceback
        traceback.print_exc()

async def view_searches_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only allow yourself to see the searches
    if update.message.from_user.id == 6822829183:  # Replace with your Telegram ID
        recent_searches = search_logger.get_recent_searches(limit=10)  # Get last 10 searches

        message = "Recent Searches:\n\n"
        for search in recent_searches:
            message += f"👤 User: {search['user_name']}\n"
            message += f"🔍 Query: {search['search_query']}\n"
            message += f"⏰ Time: {search['timestamp']}\n"
            message += f"Type: {search['search_type']}\n\n"

        await update.message.reply_text(message)
    else:
        await update.message.reply_text("You don't have permission to use this command.")


# Add this to your command handlers

class UserActivityManager:
    def __init__(self):
        self.user_activity = {}
        self.load_activity()

    def load_activity(self):
        if Path(LAST_ACTIVITY_FILE).exists():
            try:
                with open(LAST_ACTIVITY_FILE, 'rb') as f:
                    self.user_activity = pickle.load(f)
            except Exception as e:
                print(f"Error loading user activity: {e}")
                self.user_activity = {}

    def save_activity(self):
        try:
            with open(LAST_ACTIVITY_FILE, 'wb') as f:
                pickle.dump(self.user_activity, f)
        except Exception as e:
            print(f"Error saving user activity: {e}")

    def update_user_activity(self, user_id: int, user_name: str):
        self.user_activity[user_id] = {
            'last_active': datetime.now(),
            'name': user_name
        }
        self.save_activity()

    def get_inactive_users(self):
        current_time = datetime.now()
        inactive_users = []

        for user_id, data in self.user_activity.items():
            if (current_time - data['last_active']) >= INACTIVITY_THRESHOLD:
                inactive_users.append({
                    'user_id': user_id,
                    'name': data['name'],
                    'last_active': data['last_active']
                })

        return inactive_users


# Create global instance
activity_manager = UserActivityManager()


# Modify the handle_user_message function to track activity
async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    await delete_message_later(context, update.message.chat_id, update.message.message_id)
    await handle_user_query(update, context)


# Add a new function to check for inactive users
async def check_inactive_users(context: ContextTypes.DEFAULT_TYPE):
    inactive_users = activity_manager.get_inactive_users()

    for user in inactive_users:
        try:
            message = f"Hey {user['name']} 👋,\n\nI am missing you dear! 💫\nIt's been a while since we last chatted. Come back and discover some amazing movies! 🎬"

            await context.bot.send_message(
                chat_id=user['user_id'],
                text=message,
                parse_mode='Markdown'
            )

            # Update the last activity to prevent spam
            activity_manager.update_user_activity(user['user_id'], user['name'])

        except Exception as e:
            print(f"Error sending reminder to user {user['user_id']}: {e}")

class MessageTracker:
    def __init__(self):
        self.messages: Dict[int, Dict[int, datetime]] = {}

    async def add_message(self, chat_id: int, message_id: int):
        if chat_id not in self.messages:
            self.messages[chat_id] = {}
        self.messages[chat_id][message_id] = datetime.now() + timedelta(seconds=DELETE_TIMEOUT)

    async def cleanup_messages(self, context: ContextTypes.DEFAULT_TYPE):
        current_time = datetime.now()
        for chat_id in list(self.messages.keys()):
            for message_id, expiry_time in list(self.messages[chat_id].items()):
                if current_time >= expiry_time:
                    try:
                        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                    except TelegramError:
                        pass  # Message might already be deleted
                    finally:
                        del self.messages[chat_id][message_id]
            if not self.messages[chat_id]:
                del self.messages[chat_id]

message_tracker = MessageTracker()

async def cleanup_job(context: ContextTypes.DEFAULT_TYPE):
    await message_tracker.cleanup_messages(context)

async def delete_message_later(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int):
    await message_tracker.add_message(chat_id, message_id)

async def send_with_warning(message, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None, parse_mode=None):
    try:
        if hasattr(message, 'reply_text'):
            sent_message = await message.reply_text(
                f"{text}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await message.edit_text(
                f"{text}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

        await delete_message_later(context, sent_message.chat_id, sent_message.message_id)
        return sent_message
    except TelegramError as e:
        print(f"Error sending message: {e}")
        return None

async def send_photo_with_warning(message, context: ContextTypes.DEFAULT_TYPE, photo: str, caption: str, reply_markup=None, parse_mode=None):
    try:
        if hasattr(message, 'reply_photo'):
            sent_message = await message.reply_photo(
                photo=photo,
                caption=f"{caption}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await context.bot.send_photo(
                chat_id=message.chat_id,
                photo=photo,
                caption=f"{caption}\n\n{DISCLAIMER}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

        await delete_message_later(context, sent_message.chat_id, sent_message.message_id)
        return sent_message
    except TelegramError as e:
        print(f"Error sending photo: {e}")
        return None


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    keyboard = [
        [InlineKeyboardButton("  DOWNLOAD MOVIES", callback_data='search_movies')],
        [
            InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
            InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
            InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
        ],
        [InlineKeyboardButton("📈 Popular Movies", callback_data='popular'),
         InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
        [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
        [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_with_warning(
        update.message,
        context,
        f"👋 Hello {user_name}! Welcome to @movieshuba11_bot!\n\nClick on /start to restart or type",
        reply_markup=reply_markup
    )

async def show_start_menu(message, context: ContextTypes.DEFAULT_TYPE):
    # Get user's name from the callback query
    user_name = message._effective_user.first_name if hasattr(message, '_effective_user') else "there"
    keyboard = [
        [InlineKeyboardButton(" Download movies", callback_data='search_movies')],
        [
            InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
            InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
            InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
        ],
        [InlineKeyboardButton("📈 Popular Movies", callback_data='popular')],
        [InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
        [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
        [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_with_warning(
        message,
        context,
        f"👋 Hello {user_name}! Welcome to moviieshubb_bot!\n\nClick on /start to restart or type",
        reply_markup=reply_markup
    )



async def get_random_movies_by_genre(message, context: ContextTypes.DEFAULT_TYPE, genre_id=None):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "sort_by": "popularity.desc",
            "page": 1
        }

        if genre_id:
            params["with_genres"] = genre_id

        response = requests.get(url, params=params)
        response.raise_for_status()
        total_pages = min(response.json().get("total_pages", 1), 500)

        random_page = random.randint(1, total_pages)
        params["page"] = random_page

        response = requests.get(url, params=params)
        response.raise_for_status()

        all_movies = response.json().get("results", [])
        random_movies = random.sample(all_movies, min(5, len(all_movies)))

        response_text = "🎲 Random Movie Suggestions:\n\n"
        keyboard = []
        for i, movie in enumerate(random_movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"
            keyboard.append([InlineKeyboardButton(f"🔍 Search {movie['title']}", callback_data=f'search_specific_{movie["id"]}')])

        keyboard.extend([
            [
                InlineKeyboardButton("👻 Horror", callback_data='random_horror'),
                InlineKeyboardButton("🔪 Crime", callback_data='random_crime'),
                InlineKeyboardButton("💝 Romance", callback_data='random_romance')
            ],
            [InlineKeyboardButton("🎲 More Random", callback_data='random_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching random movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='random_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                                "Sorry, couldn't fetch random movies right now.",
                                reply_markup=reply_markup)


async def get_popular_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/movie/popular"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "🎬 Currently Popular Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching popular movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='popular')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch popular movies right now.",
                              reply_markup=reply_markup)

async def get_horror_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "with_genres": HORROR_GENRE_ID,
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "👻 Popular Horror Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton("👻 More Horror Movies", callback_data='horror_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching horror movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='horror_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch horror movies right now.",
                              reply_markup=reply_markup)

async def get_bollywood_popular_movies(message, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "region": "IN",
            "with_original_language": "hi",
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = "🎬  Bollywood Popular Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching Bollywood movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='bollywood_popular')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              "Sorry, couldn't fetch Bollywood movies right now.",
                              reply_markup=reply_markup)


async def search_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    special_case, special_links = special_cases_manager.is_special_case(query)
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Log the search
    search_logger.log_search(user_id, user_name, "movie", query)
    try:
        tmdb_handler = TMDBAPIHandler(TMDB_API_KEY)

        # Search for movie
        results = tmdb_handler.make_request(
            "/search/movie",
            params={"query": query, "language": "en-US"}
        ).get("results", [])

        if results:
            movie = results[0]
            movie_id = movie["id"]

            # Get movie details
            movie_details = tmdb_handler.make_request(f"/movie/{movie_id}")
            providers = tmdb_handler.make_request(f"/movie/{movie_id}/watch/providers").get("results", {}).get("US",
                                                                                                               {}).get(
                "flatrate", [])

        search_url = f"{TMDB_BASE_URL}/search/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        if results:
            movie = results[0]
            movie_id = movie["id"]

            details_url = f"{TMDB_BASE_URL}/movie/{movie_id}"
            watch_providers_url = f"{TMDB_BASE_URL}/movie/{movie_id}/watch/providers"

            details_response = requests.get(details_url, params={"api_key": TMDB_API_KEY})
            providers_response = requests.get(watch_providers_url, params={"api_key": TMDB_API_KEY})

            movie_details = details_response.json()
            providers = providers_response.json().get("results", {}).get("US", {}).get("flatrate", [])

            keyboard = [
                [InlineKeyboardButton(" Search Another Movie", callback_data='search_movies')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            response_text = (
                f"*{movie_details['title']}* ({movie_details.get('release_date', '')[:4]})\n\n"
                f"Plot: {movie_details.get('overview', 'No plot available')}\n\n"
            )

            if providers:
                response_text += "Available on: " + ", ".join(p["provider_name"] for p in providers) + "\n\n"
            else:
                response_text += "Streaming information not available\n\n"

            if special_case and special_links:
                response_text += "Download Links:\n"
                for link in special_links:
                    lang_text = f" ({link['language']})" if link.get('language') else ""
                    response_text += f"• {link['url']}{lang_text}\n"
            else:
                response_text += "download link comming soon msg @balaram129"

            if movie_details.get("poster_path"):
                poster_url = f"{TMDB_IMAGE_BASE_URL}{movie_details['poster_path']}"
                await send_photo_with_warning(update.message, context, photo=poster_url, caption=response_text, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                await send_with_warning(update.message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            keyboard = [
                [InlineKeyboardButton(" Try Again", callback_data='search_movies')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(update.message, context, "No movies found matching your search.", reply_markup=reply_markup)
    except Exception as e:
        print(f"Error in movie search: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(update.message, context,
                              "Sorry, there was an error processing your request. Please try again.",
                              reply_markup=reply_markup)

async def search_by_actor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Log the search
    search_logger.log_search(user_id, user_name, "actor", query)
    try:
        search_url = f"{TMDB_BASE_URL}/search/person"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        if results:
            actor = results[0]
            actor_id = actor["id"]

            actor_details_url = f"{TMDB_BASE_URL}/person/{actor_id}"
            movies_url = f"{TMDB_BASE_URL}/person/{actor_id}/movie_credits"

            actor_details_response = requests.get(actor_details_url, params={"api_key": TMDB_API_KEY})
            movies_response = requests.get(movies_url, params={"api_key": TMDB_API_KEY})

            actor_details = actor_details_response.json()
            movies = movies_response.json().get("cast", [])

            movies_with_rating = [m for m in movies if m.get("vote_average", 0) > 0]
            sorted_movies = sorted(movies_with_rating, key=lambda x: x.get("vote_average", 0), reverse=True)

            popular_movies = [m for m in sorted_movies if m.get("vote_average", 0) >= 7][:4]
            unpopular_movies = [m for m in sorted_movies if m.get("vote_average", 0) < 7][:4]

            response_text = f"🎭 {actor['name']}\n"
            if actor_details.get("birthday"):
                response_text += f"Birthday: {actor_details['birthday']}\n"
            if actor_details.get("place_of_birth"):
                response_text += f"Birthplace: {actor_details['place_of_birth']}\n"

            response_text += "\n📈 Highly Rated Movies:\n"
            for i, movie in enumerate(popular_movies, 1):
                response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
                response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"

            response_text += "\n📉 Other Notable Movies:\n"
            for i, movie in enumerate(unpopular_movies, 1):
                response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
                response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"

            keyboard = [
                [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
                [InlineKeyboardButton(" Search Another Actor", callback_data='search_actor')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            if actor.get("profile_path"):
                actor_image_url = f"{TMDB_IMAGE_BASE_URL}{actor['profile_path']}"
                await send_photo_with_warning(
                    update.message,
                    context,
                    photo=actor_image_url,
                    caption=response_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await send_with_warning(
                    update.message,
                    context,
                    response_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
        else:
            keyboard = [
                [InlineKeyboardButton(" Try Again", callback_data='search_actor')],
                [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                update.message,
                context,
                "No actor found matching your search.",
                reply_markup=reply_markup
            )
    except Exception as e:
        print(f"Error in actor search: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data='search_actor')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(
            update.message,
            context,
            "Sorry, there was an error processing your request. Please try again.",
            reply_markup=reply_markup
        )
def is_special_case(query):
    query_lower = query.lower().strip()
    for key, case in special_cases_manager.items():
        if query_lower == key.lower() or query_lower in [v.lower() for v in case["variants"]]:
            return True, case["links"]
    return False, []

async def get_genre_movies(message, context: ContextTypes.DEFAULT_TYPE, genre_id: int, genre_name: str):
    try:
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "with_genres": genre_id,
            "sort_by": "popularity.desc",
            "page": 1
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        movies = response.json().get("results", [])[:5]

        response_text = f"🎬 Popular {genre_name} Movies:\n\n"
        for i, movie in enumerate(movies, 1):
            response_text += f"{i}. *{movie['title']}* ({movie.get('release_date', '')[:4]})\n"
            response_text += f"Rating: ⭐ {movie.get('vote_average', 'N/A')}/10\n"
            response_text += f"Overview: {movie.get('overview', 'No overview available')[:100]}...\n\n"

        keyboard = [
            [InlineKeyboardButton(" Search These Movies", callback_data='search_movies')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context, response_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error fetching {genre_name} movies: {e}")
        keyboard = [
            [InlineKeyboardButton(" Try Again", callback_data=f'genre_{genre_name.lower()}')],
            [InlineKeyboardButton(" Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(message, context,
                              f"Sorry, couldn't fetch {genre_name} movies right now.",
                              reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_name = query.from_user.first_name

    # Update user's last activity
    activity_manager.update_user_activity(user_id, user_name)

    try:
        if query.data.startswith('search_specific_'):
            movie_id = query.data.split('_')[2]
            # Get movie details from TMDB
            url = f"{TMDB_BASE_URL}/movie/{movie_id}"
            response = requests.get(url, params={"api_key": TMDB_API_KEY})
            movie = response.json()

            # Create a message with movie details
            movie_text = f"{movie['title']} ({movie.get('release_date', '')[:4]})"

            # Send a temporary message to user's private chat
            class SimulatedMessage:
                def __init__(self, chat_id, text, from_user):
                    self.chat_id = chat_id
                    self.text = text
                    self.from_user = from_user

                def reply_text(self, *args, **kwargs):
                    return query.message.reply_text(*args, **kwargs)

                def reply_photo(self, *args, **kwargs):
                    return query.message.reply_photo(*args, **kwargs)

            # Create a proper message object
            simulated_message = SimulatedMessage(
                chat_id=query.message.chat_id,
                text=movie['title'],
                from_user=query.from_user
            )

            # Create a proper update object
            class SimulatedUpdate:
                def __init__(self, message):
                    self.message = message

            simulated_update = SimulatedUpdate(simulated_message)

            # Perform the search
            await search_movie(simulated_update, context)
            return
        if query.data == 'genre_horror':
            await get_genre_movies(query.message, context, GENRE_IDS['horror'], "Horror")
        elif query.data == 'genre_romance':
            await get_genre_movies(query.message, context, GENRE_IDS['romance'], "Romance")
        elif query.data == 'genre_crime':
            await get_genre_movies(query.message, context, GENRE_IDS['crime'], "Crime")
        elif query.data == 'random_movies':
            await get_random_movies_by_genre(query.message, context)
        if query.data == 'random_movies':
            await get_random_movies_by_genre(query.message, context)
        elif query.data == 'random_horror':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['horror'])
        elif query.data == 'random_crime':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['crime'])
        elif query.data == 'random_romance':
            await get_random_movies_by_genre(query.message, context, GENRE_IDS['romance'])
        elif query.data == 'horror_movies':
            await get_horror_movies(query.message, context)
        elif query.data == 'search_movies':
            USER_CONTEXT[query.message.chat_id] = 'movie'
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "🔍 Just type the name of any movie you want to search for!",
                reply_markup=reply_markup
            )
        elif query.data == 'search_actor':
            USER_CONTEXT[query.message.chat_id] = 'actor'
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "🎭 Just type the name of any actor to see their movies!",
                reply_markup=reply_markup
            )
        elif query.data == 'help':
            help_text = ("📖 How to use this bot:\n\n"
                        "1. Simply type any movie name\n"
                        "2. Or type any actor name to find their movies\n"
                        "3. I'll show you the details\n"
                        "4. Check out popular movies in both Hollywood and Bollywood\n"
                        "5. Try our random movie suggestions by genre!\n"
                        "Need more help? Just type /start to see the main menu again! or msg @balaram129")
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                help_text,
                reply_markup=reply_markup
            )
        elif query.data == 'popular':
            await get_popular_movies(query.message, context)
        elif query.data == 'bollywood_popular':
            await get_bollywood_popular_movies(query.message, context)
        elif query.data == 'start_menu':
            keyboard = [
                [InlineKeyboardButton("🔍 Download movies", callback_data='search_movies'),
                 InlineKeyboardButton("👻 Horror Movies", callback_data='horror_movies')],
                [
                    InlineKeyboardButton("👻 Horror", callback_data='genre_horror'),
                    InlineKeyboardButton("💝 Romance", callback_data='genre_romance'),
                    InlineKeyboardButton("🔪 Crime", callback_data='genre_crime')
                ],
                [InlineKeyboardButton("📈 Popular Movies", callback_data='popular')],
                [InlineKeyboardButton("🎲 Random Movies", callback_data='random_movies')],
                [InlineKeyboardButton("🎬 Bollywood Popular", callback_data='bollywood_popular')],
                [InlineKeyboardButton("🎭 Search by Actor", callback_data='search_actor')],
                [InlineKeyboardButton("❓ Help", callback_data='help')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_with_warning(
                query.message,
                context,
                "👋 Welcome to moviieshubb_bot!\n\nClick on /start to restart or type",
                reply_markup=reply_markup
            )

    except Exception as e:
        print(f"Error in button callback: {e}")
        keyboard = [
            [InlineKeyboardButton("🏠 Main Menu", callback_data='start_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_with_warning(
            query.message,
            context,
            "Sorry, there was an error processing your request. Please try again.",
            reply_markup=reply_markup
        )

async def handle_user_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_context = USER_CONTEXT.get(update.message.chat_id, "movie")
    if user_context == "actor":
        await search_by_actor(update, context)
    else:
        await search_movie(update, context)

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_message_later(context, update.message.chat_id, update.message.message_id)
    await handle_user_query(update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Exception while handling an update: {context.error}")
    if isinstance(context.error, Conflict):
        print("Bot instance already running. Exiting...")
        sys.exit(1)
    elif isinstance(context.error, NetworkError):
        print("Network error occurred. Waiting before retry...")
        await asyncio.sleep(1)
    else:
        print(f"Unexpected error: {context.error}")


def main():
    try:
        application = (
            Application.builder()
            .token(TELEGRAM_TOKEN)
            .build()
        )

        # Add existing handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CallbackQueryHandler(button_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))
        application.add_handler(CommandHandler("viewsearches", view_searches_command))

        # Add error handler
        application.add_error_handler(error_handler)

        # Set up the cleanup job to run every 10 seconds
        job_queue = application.job_queue
        job_queue.run_repeating(cleanup_job, interval=10, first=0)

        # Add the inactive user check job (runs every 6 hours)
        job_queue.run_repeating(check_inactive_users, interval=21600, first=21600)

        # Update stastics more frequently (every 5 minutes)
        job_queue.run_repeating(update_stastics_job, interval=300, first=0)

        # Initial statistics update
        print("Performing initial statistics update...")
        stats = SearchStatistics()
        stats.update_stastics_file()
        print("Initial statistics update completed")

        # Start the bot
        print("Starting bot...")
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

    except Exception as e:
        print(f"Error starting bot: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

# Test the logger
logger = SearchLogger()
logger.log_search(123456, "TestUser", "movie", "Avatar")

# Check recent searches
recent = logger.get_recent_searches()
print("Recent searches:", recent)