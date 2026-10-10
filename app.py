import base64
import streamlit as st
import requests
import hashlib
import json
import time
import uuid
from io import BytesIO
from PIL import Image
from google import genai
from google.genai import types
# SUPABASE DATABASE DRIVER
import psycopg2


# =========================================================
# PAGE CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="Nature Encyclopedia AI",
    page_icon="🌍",
    layout="wide"
)

 

 
# =========================================================
# SESSION STATE
# =========================================================

defaults = {
    "page": "home",
    "image_bytes": None,
    "image_hash": None,
    "ai_result": None,
    "ai_model_used": None,
    "selected_taxon": None,
    "selected_observations": [],
    "search_name": "",
    "home_nature_image": None,
    # =====================================================
    # GOGY & TITLI AI
    # =====================================================

    "active_character": "gogy",
     
# Separate chat histories for each character
"gogy_conversation": [],
"titli_conversation": [],

# Keep the existing setting for compatibility
"character_conversation": [],
    
    "voice_enabled": True,
    "audio_enabled": True,
    "last_audio": None,
    "audio_character": None,
    "audio_error": None,
    "gogy_expression": "happy",
    "titli_expression": "happy",
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

# =========================================================
# SUPABASE CHAT STORAGE
# A browser-local ID keeps saved chats available after closing/reopening
# the app in the same browser profile. This is NOT user authentication.
# Add proper login before making private conversations public.
# =========================================================

# Store a stable, per-browser chat ID in localStorage.
# Streamlit components return it to Python and trigger a rerun.
BROWSER_CHAT_ID_COMPONENT = st.components.v2.component(
    name="nature_chat_browser_identity",
    html="<div style='font-size:11px;color:#888'>Preparing saved chats…</div>",
    css="",
    js="""
    export default function(component) {
        const { setTriggerValue } = component;
        let owner = "";
        try {
            owner = localStorage.getItem("nature_ai_chat_owner") || "";
            if (!owner) {
                // Reuse the old URL token once, so earlier saved chats can still be found.
                const oldUrlOwner = new URL(window.location.href).searchParams.get("chat_owner");
                owner = oldUrlOwner || (
                    (window.crypto && crypto.randomUUID)
                        ? crypto.randomUUID()
                        : ("chat-" + Date.now().toString(36) + "-" +
                           Math.random().toString(36).slice(2))
                );
                localStorage.setItem("nature_ai_chat_owner", owner);
            }
        } catch (e) {
            owner = "temporary-" + Math.random().toString(36).slice(2);
        }
        setTriggerValue("owner", owner);
        return () => {};
    }
    """
)
_browser_identity = BROWSER_CHAT_ID_COMPONENT(key="nature_ai_chat_browser_identity")
_browser_owner = getattr(_browser_identity, "owner", None)

# Backward-compatible fallback for older URLs/browser restrictions.
try:
    _query_chat_owner = st.query_params.get("chat_owner")
except Exception:
    _query_chat_owner = None

_chat_owner = str(_browser_owner or _query_chat_owner or uuid.uuid4())
st.session_state.chat_session_id = _chat_owner

if "current_chat_ids" not in st.session_state:
    st.session_state.current_chat_ids = {"gogy": None, "titli": None}


def encode_chat_image(image_bytes):
    """Resize/compress an uploaded chat photo before saving it with the message."""
    if not image_bytes:
        return None
    try:
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        image.thumbnail((1280, 1280))
        output = BytesIO()
        image.save(output, format="JPEG", quality=82, optimize=True)
        return base64.b64encode(output.getvalue()).decode("ascii")
    except Exception:
        return None


def decode_chat_image(image_base64):
    """Decode an image stored with a saved conversation message."""
    if not image_base64:
        return None
    try:
        return base64.b64decode(image_base64)
    except Exception:
        return None


def get_chat_db_connection():
    """Open a secure SSL connection to the Supabase Postgres database."""
    db_url = st.secrets.get("SUPABASE_DB_URL", "")
    if not db_url:
        return None
    return psycopg2.connect(db_url, connect_timeout=10, sslmode="require")


def ensure_chat_table():
    """Create the chat table and index if they do not already exist."""
    connection = get_chat_db_connection()
    if connection is None:
        return False
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS nature_ai_chats (
                        chat_id UUID PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        character TEXT NOT NULL CHECK (character IN ('gogy', 'titli')),
                        title TEXT NOT NULL,
                        messages JSONB NOT NULL DEFAULT '[]'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS nature_ai_chats_session_updated_idx
                    ON nature_ai_chats (session_id, updated_at DESC)
                """)
        return True
    finally:
        connection.close()


def save_chat_to_supabase(character, messages, chat_id=None, custom_title=None):
    """Safely insert/update one chat without reusing a conflicting primary key.

    Returns (success, saved_chat_id, error_message). If the supplied ID is stale
    or belongs to a different browser session, create a fresh UUID rather than
    attempting to insert the conflicting ID again.
    """
    if not messages:
        return False, chat_id, "There are no messages to save yet."

    connection = None
    try:
        if not ensure_chat_table():
            return False, chat_id, "SUPABASE_DB_URL is missing from Streamlit Secrets."

        connection = get_chat_db_connection()
        session_id = str(st.session_state.chat_session_id)
        new_chat_id = str(chat_id or uuid.uuid4())

        first_user_message = next(
            (str(item.get("content", "")).strip() for item in messages
             if item.get("role") == "user" and str(item.get("content", "")).strip()),
            "Conversation with " + character.capitalize()
        )
        title = (str(custom_title).strip() if custom_title else first_user_message)[:120]
        if not title:
            title = first_user_message[:120]
        messages_json = json.dumps(messages, ensure_ascii=False)

        with connection:
            with connection.cursor() as cursor:
                # First, update only a row owned by this browser session and character.
                if chat_id:
                    cursor.execute("""
                        UPDATE nature_ai_chats
                        SET title = %s, messages = %s::jsonb, updated_at = NOW()
                        WHERE chat_id = %s AND session_id = %s AND character = %s
                    """, (title, messages_json, new_chat_id, session_id, character))
                    if cursor.rowcount > 0:
                        return True, new_chat_id, None

                    # If update missed, check whether the ID exists but is stale or
                    # belongs to another session/character. Never overwrite that row.
                    cursor.execute("""
                        SELECT session_id, character
                        FROM nature_ai_chats
                        WHERE chat_id = %s
                    """, (new_chat_id,))
                    existing = cursor.fetchone()
                    if existing:
                        # A matching owner may have changed concurrently; retry a
                        # constrained update before deciding to create a fresh ID.
                        if str(existing[0]) == session_id and existing[1] == character:
                            cursor.execute("""
                                UPDATE nature_ai_chats
                                SET title = %s, messages = %s::jsonb, updated_at = NOW()
                                WHERE chat_id = %s AND session_id = %s AND character = %s
                            """, (title, messages_json, new_chat_id, session_id, character))
                            if cursor.rowcount > 0:
                                return True, new_chat_id, None
                        # Existing ID cannot safely be reused. Use a new UUID.
                        new_chat_id = str(uuid.uuid4())

                # Insert with a fresh ID. ON CONFLICT is a final race-condition
                # guard; it updates only when the row belongs to this same session
                # and character. If it cannot safely update, retry with a fresh ID.
                for attempt in range(3):
                    cursor.execute("""
                        INSERT INTO nature_ai_chats
                            (chat_id, session_id, character, title, messages)
                        VALUES (%s, %s, %s, %s, %s::jsonb)
                        ON CONFLICT (chat_id) DO UPDATE
                        SET title = EXCLUDED.title,
                            messages = EXCLUDED.messages,
                            updated_at = NOW()
                        WHERE nature_ai_chats.session_id = EXCLUDED.session_id
                          AND nature_ai_chats.character = EXCLUDED.character
                        RETURNING chat_id
                    """, (new_chat_id, session_id, character, title, messages_json))
                    saved_row = cursor.fetchone()
                    if saved_row:
                        return True, str(saved_row[0]), None
                    new_chat_id = str(uuid.uuid4())

        return False, None, "Could not create a unique saved-chat ID after several attempts. Please retry."

    except Exception as exc:
        return False, chat_id, f"{type(exc).__name__}: {exc}"
    finally:
        if connection is not None:
            connection.close()


def get_saved_chats(character):
    """Return saved chats for the current Streamlit session only."""
    connection = None
    try:
        if not ensure_chat_table():
            return [], "SUPABASE_DB_URL is missing from Streamlit Secrets."
        connection = get_chat_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT chat_id::text, title, messages, updated_at
                FROM nature_ai_chats
                WHERE session_id = %s AND character = %s
                ORDER BY updated_at DESC
                LIMIT 1000
            """, (st.session_state.chat_session_id, character))
            rows = cursor.fetchall()
        return [
            {"chat_id": row[0], "title": row[1],
             "messages": row[2] if isinstance(row[2], list) else json.loads(row[2]),
             "updated_at": row[3]}
            for row in rows
        ], None
    except Exception as exc:
        return [], str(exc)
    finally:
        if connection is not None:
            connection.close()


def delete_chat_from_supabase(chat_id):
    """Delete only a chat owned by the current Streamlit session."""
    connection = None
    try:
        if not ensure_chat_table():
            return False, "SUPABASE_DB_URL is missing from Streamlit Secrets."
        connection = get_chat_db_connection()
        with connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    DELETE FROM nature_ai_chats
                    WHERE chat_id = %s AND session_id = %s
                """, (chat_id, st.session_state.chat_session_id))
                deleted = cursor.rowcount > 0
        return deleted, None if deleted else "Chat not found in this session."
    except Exception as exc:
        return False, str(exc)
    finally:
        if connection is not None:
            connection.close()# =========================================================
# iNATURALIST API
# =========================================================

INAT_TAXA_URL = (
    "https://api.inaturalist.org/v1/taxa/autocomplete"
)

INAT_OBSERVATIONS_URL = (
    "https://api.inaturalist.org/v1/observations"
)

HEADERS = {
    "User-Agent": "Nature-Encyclopedia-AI/1.0"
}



 
# ==========================================
# iNATURALIST TAXON SEARCH
# ==========================================

@st.cache_data(
    ttl=3600,
    show_spinner=False
)
def search_taxon_cached(search_name):
    try:
        response = requests.get(
            INAT_TAXA_URL,
            params={
                "q": search_name.strip(),
                "per_page": 10
            },
            headers=HEADERS,
            timeout=15
        )

        response.raise_for_status()

        results = response.json().get("results", [])

        if not results:
            return None

        # SEARCH FIX: Normalize singular and plural names.
        def normalize_name(value):
            words = (
                (value or "")
                .lower()
                .replace("-", " ")
                .split()
            )

            irregular = {
                "mice": "mouse",
                "mouse": "mouse",
                "rats": "rat",
                "rat": "rat",
                "hamsters": "hamster",
                "hamster": "hamster",
                "butterflies": "butterfly",
                "butterfly": "butterfly",
                "flies": "fly",
                "fly": "fly",
                "wolves": "wolf",
                "wolf": "wolf",
                "geese": "goose",
                "goose": "goose",
                "deer": "deer",
                "sheep": "sheep",
            }

            normalized = []

            for word in words:
                if word in irregular:
                    word = irregular[word]
                elif len(word) > 4 and word.endswith("ies"):
                    word = word[:-3] + "y"
                elif (
                    len(word) > 3
                    and word.endswith("s")
                    and not word.endswith("ss")
                ):
                    word = word[:-1]

                normalized.append(word)

            return " ".join(normalized)

        # Normalize the user's search.
        search_normalized = normalize_name(search_name)
        search_words = set(search_normalized.split())

        # SEARCH FIX: Find the closest relevant organism.
        best_match = None
        best_score = 0

        for taxon in results:
            common_name = normalize_name(
                taxon.get("preferred_common_name")
            )

            scientific_name = normalize_name(
                taxon.get("name")
            )

            # Exact match has the highest priority.
            if (
                common_name == search_normalized
                or scientific_name == search_normalized
            ):
                return taxon

            # Match words in the organism's names.
            common_words = set(common_name.split())
            scientific_words = set(scientific_name.split())

            score = (
                len(search_words & common_words) * 3
                + len(search_words & scientific_words)
            )

            if score > best_score:
                best_score = score
                best_match = taxon

        # Do not show an unrelated organism.
        if best_score > 0:
            return best_match

        return None

    except Exception as e:
        return {
            "error": str(e)
}# =========================================================
# iNATURALIST OBSERVATIONS
# =========================================================

@st.cache_data(
    ttl=3600,
    show_spinner=False
)
def get_observations_cached(taxon_id):

    try:

        response = requests.get(
            INAT_OBSERVATIONS_URL,
            params={
                "taxon_id": taxon_id,
                "photos": "true",
                "quality_grade": "research",
                "order_by": "votes",
                "order": "desc",
                "per_page": 6
            },
            headers=HEADERS,
            timeout=20
        )

        response.raise_for_status()

        return response.json().get(
            "results",
            []
        )

    except Exception:

        return []
        # =========================================================
# LARGE PHOTO URL
# =========================================================

def get_large_photo_url(photo):

    if not photo:
        return None

    url = photo.get("url")

    if not url:
        return None

    url = url.replace(
        "/square.",
        "/large."
    )

    url = url.replace(
        "/small.",
        "/large."
    )

    url = url.replace(
        "/medium.",
        "/large."
    )

    return url


# =========================================================
# GEMINI SETUP
# =========================================================

# Keep the setup failure so a missing/invalid secret does not silently
# look like a temporary network problem in the chat UI.
GEMINI_SETUP_ERROR = None

try:
    GEMINI_API_KEY = str(st.secrets["GEMINI_API_KEY"]).strip()
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is empty.")

    gemini_client = genai.Client(api_key=GEMINI_API_KEY)

except Exception as setup_exc:
    GEMINI_SETUP_ERROR = f"{type(setup_exc).__name__}: {setup_exc}"
    gemini_client = None
    print("[Goggy & Titli] Gemini client setup failed: " + GEMINI_SETUP_ERROR)


# =========================================================
# GEMINI MODELS
# =========================================================

GEMINI_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    
    
]


# =========================================================
# GEMINI IMAGE IDENTIFICATION
# =========================================================

def identify_with_model(
    image_bytes,
    model_name
):

    image = Image.open(
        BytesIO(image_bytes)
    )

    prompt = """
Look carefully at this image.

Identify the main living organism.

It may be:
- an animal
- a plant
- another clearly identifiable living organism

Focus mainly on animals and plants.

Return ONLY valid JSON in exactly this format:

{
  "type": "animal or plant",
  "common_name": "common name",
  "scientific_name": "scientific name if reasonably identifiable, otherwise empty string",
  "confidence": 0,
  "reason": "short explanation based on visible features"
}

Rules:

1. Do not invent a species.
2. If species-level identification is uncertain,
   identify the broader organism.
3. Confidence must be between 0 and 100.
4. Keep the reason short.
5. Return JSON only.
"""

    response = (
        gemini_client
        .models
        .generate_content(
            model=model_name,
            contents=[
                prompt,
                image
            ]
        )
    )

    text = response.text.strip()

    # Remove Markdown code fences
    if text.startswith("```"):

        text = text.replace(
            "```json",
            "",
            1
        )

        text = text.replace(
            "```",
            ""
        )

        text = text.strip()

    # Find JSON inside response
    if not text.startswith("{"):

        start = text.find("{")
        end = text.rfind("}")

        if start != -1 and end != -1:
            text = text[start:end + 1]

    return json.loads(text)

# =========================================================
# GEMINI IDENTIFICATION
# =========================================================

@st.cache_data(
    ttl=3600,
    show_spinner=False
)
def identify_organism_cached(
    image_bytes,
    image_hash
):

    if gemini_client is None:

        return {
            "success": False,
            "error": (
                "GEMINI_API_KEY is missing "
                "or invalid."
            ),
            "model": None
        }

    errors = []

    for model_name in GEMINI_MODELS:

        for attempt in range(2):

            try:

                result = identify_with_model(
                    image_bytes,
                    model_name
                )

                return {
                    "success": True,
                    "result": result,
                    "model": model_name,
                    "error": None
                }

            except Exception as e:

                errors.append(
                    f"{model_name} "
                    f"attempt {attempt + 1}: "
                    f"{str(e)}"
                )

                if attempt == 0:
                    time.sleep(2)

    return {
        "success": False,
        "error": "\n\n".join(errors),
        "model": None
    }# =========================================================
# ORGANISM TYPE
# =========================================================

def determine_organism_type(
    taxon,
    ai_result=None
):

    if ai_result:

        ai_type = str(
            ai_result.get(
                "type",
                ""
            )
        ).lower()

        if ai_type in [
            "animal",
            "plant"
        ]:

            return ai_type

    major_group = str(
        taxon.get(
            "iconic_taxon_name",
            ""
        )
    ).lower()

    if major_group == "plantae":
        return "plant"

    if major_group == "animalia":
        return "animal"

    return "organism"# =========================================================
# SPECIES PAGE
# =========================================================

def show_species_page(
    taxon,
    observations,
    ai_result=None
):

    if not taxon:

        st.warning(
            "Species information could not be found."
        )

        return

    if taxon.get("error"):

        st.error(
            "iNaturalist error: "
            + str(taxon["error"])
        )

        return

    common_name = (
        taxon.get(
            "preferred_common_name"
        )
        or taxon.get("name")
        or "Unknown"
    )

    scientific_name = (
        taxon.get("name")
        or "Unknown"
    )

    rank = (
        taxon.get("rank")
        or "Unknown"
    )

    major_group = (
        taxon.get("iconic_taxon_name")
        or "Unknown"
    )

    organism_type = determine_organism_type(
        taxon,
        ai_result
)# =====================================================
    # HEADER
    # =====================================================

    if organism_type == "plant":

        st.title(
            "🌱 " + common_name
        )

    elif organism_type == "animal":

        st.title(
            "🐾 " + common_name
        )

    else:

        st.title(
            "🌍 " + common_name
        )

    st.markdown(
        "### *" + scientific_name + "*"
    )

    # =====================================================
    # BASIC INFORMATION
    # =====================================================

    st.subheader(
        "📚 Basic Information"
    )

    col1, col2 = st.columns(2)

    with col1:

        st.write(
            "**Scientific name:** *"
            + scientific_name
            + "*"
        )

        st.write(
            "**Taxonomic rank:** "
            + rank
        )

    with col2:

        st.write(
            "**Major group:** "
            + major_group
        )

        if organism_type == "plant":

            st.write(
                "**Type:** 🌱 Plant"
            )

        elif organism_type == "animal":

            st.write(
                "**Type:** 🐾 Animal"
            )

        else:

            st.write(
                "**Type:** 🌍 Living organism"
            )

    # =====================================================
    # MAIN PHOTO
    # =====================================================

    default_photo = taxon.get(
        "default_photo"
    )

    if default_photo:

        photo_url = get_large_photo_url(
            default_photo
        )

        if photo_url:

            st.subheader(
                "📸 Photograph"
            )

            st.image(
                photo_url,
                use_container_width=True
    )# =====================================================
    # AI DETAILS
    # =====================================================

    if ai_result:

        confidence = ai_result.get(
            "confidence"
        )

        if confidence is not None:

            st.write(
                "**Identification confidence:** "
                + str(confidence)
                + "%"
            )

        reason = ai_result.get(
            "reason",
            ""
        )

        if reason:

            st.write(
                "**Identification reason:** "
                + str(reason)
            )

    # =====================================================
    # MORE INFORMATION
    # =====================================================

    st.divider()

    st.subheader(
        "🔬 More Information"
    )

    taxon_id = taxon.get("id")

    if taxon_id:

        inat_url = (
            "https://www.inaturalist.org/taxa/"
            + str(taxon_id)
        )

        st.link_button(
            "🌿 Explore on iNaturalist",
            inat_url,
            use_container_width=True
        )

    # =====================================================
    # MORE PHOTOS
    # =====================================================

    if observations:

        st.divider()

        st.subheader(
            "📷 More iNaturalist Photographs"
        )

        photo_urls = []

        for observation in observations:

            photos = observation.get(
                "photos",
                []
            )

            if photos:

                photo_url = (
                    get_large_photo_url(
                        photos[0]
                    )
                )

                if photo_url:
                    photo_urls.append(
                        photo_url
                    )

        if photo_urls:

            st.image(
                photo_urls,
                use_container_width=True
            )
# =========================================================
# HOME PAGE
# =========================================================

def show_home():

    st.title("🌍 Nature Encyclopedia AI")

    st.subheader(
        "Explore the living world with Gogy & Titli 🦋"
    )

    st.write(
        "Ask a question, search for an organism, "
        "or identify something from a photograph."
    )

    st.divider()

    # =====================================================
    # GOGY AND TITLI
    # =====================================================

    col1, col2 = st.columns(2)

    with col1:

        st.markdown("## 🧒 Gogy")

        st.write(
            "👋 Hi! I'm Gogy! "
            "I love discovering how nature works."
        )

        if st.button(
            "💬 Talk to Gogy",
            type="primary",
            use_container_width=True,
            key="talk_to_gogy"
        ):

            st.session_state.active_character = "gogy"
            st.session_state.page = "conversation"

            st.rerun()

    with col2:

        st.markdown("## 👧🦋 Titli")

        st.write(
            "🦋 Hiii! I'm Titli! "
            "Ooooh! Let's discover something amazing!"
        )

        if st.button(
            "💬 Talk to Titli",
            use_container_width=True,
            key="talk_to_titli"
        ):

            st.session_state.active_character = "titli"
            st.session_state.page = "conversation"

            st.rerun()

    st.divider()# =====================================================
    # SEARCH
    # =====================================================

    st.header("🔎 What do you want to know?")

    with st.form("home_search_form"):

        search_name = st.text_input(
            "Search organism",
            placeholder=(
                "Tiger, frog, butterfly, neem..."
            )
        )

        submitted = st.form_submit_button(
            "🔎 Explore Nature",
            use_container_width=True
        )

    if submitted:

        if not search_name.strip():

            st.warning(
                "Please enter an animal or plant."
            )

        else:

            st.session_state.search_name = (
                search_name.strip()
            )

            with st.spinner(
                "🌿 Finding this organism..."
            ):

                taxon = search_taxon_cached(
                    search_name.strip()
                )

                if (
                    taxon
                    and not taxon.get("error")
                ):

                    taxon_id = taxon.get("id")

                    observations = []

                    if taxon_id:

                        observations = (
                            get_observations_cached(
                                taxon_id
                            )
                        )

                    st.session_state.selected_taxon = (
                        taxon
                    )

                    st.session_state.selected_observations = (
                        observations
                    )

                    st.session_state.page = "search"

                    st.rerun()

                elif (
                    taxon
                    and taxon.get("error")
                ):

                    st.error(
                        "iNaturalist error: "
                        + str(taxon["error"])
                    )

                else:

                    st.warning(
                        "I couldn't find that organism."
                    )

    st.divider()

    # =====================================================
    # OTHER OPTIONS
    # =====================================================

    col1, col2 = st.columns(2)

    with col1:

        st.subheader("🌿 Explore Flora & Fauna")

        st.write(
            "Search animals and plants and "
            "explore biodiversity information."
        )

        if st.button(
            "Explore Flora & Fauna",
            use_container_width=True,
            key="explore_home"
        ):

            st.session_state.page = "search"

            st.session_state.search_name = ""

            st.session_state.selected_taxon = None

            st.session_state.selected_observations = []

            st.rerun()

    with col2:

        st.subheader("📷 Identify from Photo")

        st.write(
            "Upload a photograph and let AI "
            "identify the organism."
        )

        if st.button(
            "Identify from Photo",
            use_container_width=True,
            key="identify_home"
        ):

            st.session_state.page = "identify"

            st.rerun()

    st.divider()

    st.caption(
        "🌿 Biodiversity data and photographs "
        "are retrieved from iNaturalist."
)# =========================================================
# AUDIO ARCHITECTURE
# =========================================================

def prepare_audio(audio_bytes, character):
    """
    Stores generated character audio in session state.

    Later this will receive audio generated by:
    Gogy  -> AI Two / Finn
    Titli -> SpeechGen voice

    For now it only prepares the architecture.
    """

    if not audio_bytes:
        return

    st.session_state.last_audio = audio_bytes
    st.session_state.audio_character = character


def play_character_audio():
    """
    Plays the latest character audio.
    """

    audio_bytes = st.session_state.get("last_audio")

    if not audio_bytes:
        return

    if not st.session_state.get("audio_enabled", True):
        return

    st.audio(audio_bytes, format="audio/mp3")


def clear_character_audio():
    """
    Clears previously generated character audio.
    """

    st.session_state.last_audio = None
    st.session_state.audio_character = None
# =========================================================
# CHARACTER VOICE GENERATORS
# Paid TTS was replaced by the free browser speech function below.
# Keep this section marker so the surrounding app structure stays clear.
# =========================================================

# =========================================================
# FREE BUILT-IN BROWSER SPEECH — NO API KEY OR CREDITS
# Uses the browser/device speech voices for Hindi and English.
# The selected browser voice may vary by device and installed languages.
# =========================================================

def speak_character_text(character, text):
    """Speak text in the browser using built-in speech synthesis."""
    if not text or not st.session_state.get("audio_enabled", True):
        return

    # JSON encoding safely escapes quotes/newlines before inserting text into JS.
    text_json = json.dumps(str(text))
    character_json = json.dumps(str(character))
    html = f"""
    <!doctype html><html><head><meta charset="utf-8"></head>
    <body style="margin:0;font:12px sans-serif;color:#666">
    <span id="speech-status">Preparing free voice…</span>
    <script>
    (() => {{
      const rawText = {text_json};
      const character = {character_json};
      const status = document.getElementById('speech-status');

      // Remove Markdown and formatting symbols before speaking.
      const cleanSpeechText = (value) => String(value || '')
        .replace(/```[\\s\\S]*?```/g, ' ')
        .replace(/`([^`]+)`/g, '$1')
        .replace(/!\\[([^\\]]*)\\]\\([^)]+\\)/g, '$1')
        .replace(/\\[([^\\]]+)\\]\\([^)]+\\)/g, '$1')
        .replace(/https?:\\/\\/\\S+/g, ' ')
        .replace(/^\\s{{0,3}}#{{1,6}}\\s*/gm, '')
        .replace(/^\\s*>\\s?/gm, '')
        .replace(/^\\s*[-+]\\s+/gm, '')
        .replace(/^\\s*\\*\\s+/gm, '')
        .replace(/\\*\\*([\\s\\S]*?)\\*\\*/g, '$1')
        .replace(/__([\\s\\S]*?)__/g, '$1')
        .replace(/~~([\\s\\S]*?)~~/g, '$1')
        .replace(/\\[\\^?\\d+\\]/g, ' ')
        .replace(/₹/g, ' रुपये ')
        .replace(/[$*_~#`]/g, ' ')
        .replace(/[()\\[\\]]/g, ' ')
        .replace(/[{{}}]/g, ' ')
        .replace(/\\s+/g, ' ')
        .trim();

      const text = cleanSpeechText(rawText);
      if (!text) {{
        status.textContent = 'Nothing readable to speak.';
        return;
      }}
      try {{
        if (!('speechSynthesis' in window) || !('SpeechSynthesisUtterance' in window)) {{
          status.textContent = 'This browser does not support built-in speech. Try Chrome.';
          return;
        }}
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(text);
        // Detect Devanagari text and explicitly request the correct language.
        const hasHindi = /[\\u0900-\\u097F]/.test(text);
        utterance.lang = hasHindi ? 'hi-IN' : 'en-IN';
        // Keep the characters distinct, while slowing Hindi slightly for clarity.
        utterance.rate = hasHindi
          ? (character === 'titli' ? 0.90 : 0.88)
          : (character === 'titli' ? 1.02 : 0.96);
        utterance.pitch = character === 'titli' ? 1.18 : 0.96;
        let started = false;
        const chooseVoice = () => {{
          if (started) return;
          const voices = window.speechSynthesis.getVoices() || [];
          // Prefer an exact Hindi (India) voice; otherwise use another Hindi voice.
          // Never deliberately select an English voice for Hindi text.
          const langPrefix = hasHindi ? 'hi' : 'en';
          const candidates = voices.filter(v => (v.lang || '').toLowerCase().startsWith(langPrefix));
          const matching = hasHindi
            ? (candidates.find(v => (v.lang || '').toLowerCase() === 'hi-in') || candidates[0])
            : (candidates.find(v => (v.lang || '').toLowerCase() === 'en-in') || candidates[0]);
          // Wait for the browser's voice list when it is not ready yet.
          if (!matching && voices.length === 0 && !chooseVoice.waited) {{
            chooseVoice.waited = true;
            setTimeout(chooseVoice, 700);
            return;
          }}
          started = true;
          if (matching) utterance.voice = matching;
          status.textContent = matching
            ? ('🔊 ' + (character === 'titli' ? 'Titli' : 'Goggy') + ' speaking (' + matching.lang + ')')
            : (hasHindi ? 'Hindi voice not found in this browser; check Google TTS Hindi voice installation.' : 'Using the browser default English voice');
          window.speechSynthesis.speak(utterance);
        }};
        const voices = window.speechSynthesis.getVoices();
        if (voices.length) chooseVoice();
        else {{
          window.speechSynthesis.onvoiceschanged = chooseVoice;
          // Some mobile browsers do not fire onvoiceschanged reliably.
          setTimeout(() => {{ if (window.speechSynthesis.pending === false) chooseVoice(); }}, 250);
        }}
        utterance.onend = () => {{ status.textContent = 'Voice finished'; }};
        utterance.onerror = () => {{ status.textContent = 'Voice unavailable; check device text-to-speech settings.'; }};
      }} catch (e) {{ status.textContent = 'Built-in voice could not start. Try tapping Speak again.'; }}
    }})();
    </script></body></html>
    """
    st.components.v1.html(html, height=28, scrolling=False)# =========================================================
# 🎙️ REAL VOICE INPUT — SPEECH RECOGNITION
# =========================================================
#
# This section connects:
#
# 🎙️ Microphone
#      ↓
# 🎵 Listening animation
#      ↓
# Browser speech recognition
#      ↓
# Text sent back to Python
#
# The existing Gemini + ElevenLabs system will use
# this text later through a small hook in show_conversation().
#
# IMPORTANT:
# This keeps the microphone UI and listening animation
# inside the same voice component.
# =========================================================

VOICE_INPUT_COMPONENT = st.components.v2.component(
    name="nature_voice_input",

    html="""
    <div class="voice-box">

        <div id="notes" class="notes">
            🎵 ♪ ♫ ♪ 🎵
        </div>

        <button id="mic" class="mic">
            🎙️
        </button>

        <div id="listening" class="listening">
            Listening...
        </div>

        <div id="voice-status" class="voice-status"></div>

    </div>
    """,

    css="""
    .voice-box {
        text-align: center;
        padding: 8px;
    }

    .mic {
        width: 58px;
        height: 58px;
        border-radius: 50%;
        border: none;
        background: #222;
        color: white;
        font-size: 28px;
        cursor: pointer;
    }

    .mic:active {
        transform: scale(0.95);
    }

    .notes {
        display: none;
        font-size: 25px;
        animation: float 1s infinite alternate;
        margin-bottom: 4px;
    }

    .listening {
        display: none;
        margin-top: 8px;
        font-size: 14px;
    }

    .voice-status {
        margin-top: 6px;
        font-size: 12px;
    }

    @keyframes float {
        from {
            transform: translateY(5px);
        }

        to {
            transform: translateY(-8px);
        }
    }
    """,

    js="""
    export default function(component) {

        const {
            parentElement,
            setTriggerValue
        } = component;

        const mic =
            parentElement.querySelector("#mic");

        const notes =
            parentElement.querySelector("#notes");

        const listening =
            parentElement.querySelector("#listening");

        const status =
            parentElement.querySelector("#voice-status");


        // ---------------------------------------------
        // Browser Speech Recognition
        // ---------------------------------------------

        const SpeechRecognition =
            window.SpeechRecognition ||
            window.webkitSpeechRecognition;


        let recognition = null;
        let active = false;


        // ---------------------------------------------
        // Browser support check
        // ---------------------------------------------

        if (!SpeechRecognition) {

            mic.disabled = true;

            status.textContent =
                "Voice input is not supported in this browser.";

            return;
        }


        // ---------------------------------------------
        // Create speech recognition
        // ---------------------------------------------

        recognition = new SpeechRecognition();

        recognition.lang = "hi-IN";

        recognition.continuous = false;

        recognition.interimResults = false;


        // ---------------------------------------------
        // MICROPHONE BUTTON
        // ---------------------------------------------

        mic.onclick = () => {

            if (active) {

                recognition.stop();

                return;
            }


            try {

                active = true;

                notes.style.display = "block";

                listening.style.display = "block";

                status.textContent = "";


                recognition.start();

            } catch (error) {

                active = false;

                notes.style.display = "none";

                listening.style.display = "none";

                status.textContent =
                    "Could not start microphone.";

            }
        };


        // ---------------------------------------------
        // SPEECH RESULT
        // ---------------------------------------------

        recognition.onresult = (event) => {

            let transcript = "";

            for (
                let i = event.resultIndex;
                i < event.results.length;
                i++
            ) {

                if (
                    event.results[i].isFinal
                ) {

                    transcript +=
                        event.results[i][0].transcript;
                }
            }


            transcript =
                transcript.trim();


            if (transcript) {

                // Send completed speech to Python.
                //
                // This is a one-time trigger,
                // so the same sentence will not
                // remain permanently in the component.

                setTriggerValue(
                    "speech",
                    transcript
                );
            }
        };


        // ---------------------------------------------
        // RECOGNITION ENDED
        // ---------------------------------------------

        recognition.onend = () => {

            active = false;

            notes.style.display = "none";

            listening.style.display = "none";
        };


        // ---------------------------------------------
        // RECOGNITION ERROR
        // ---------------------------------------------

        recognition.onerror = (event) => {

            active = false;

            notes.style.display = "none";

            listening.style.display = "none";


            if (
                event.error === "not-allowed"
            ) {

                status.textContent =
                    "Microphone permission is required.";

            } else if (
                event.error === "no-speech"
            ) {

                status.textContent =
                    "I couldn't hear anything.";

            } else {

                status.textContent =
                    "Voice input error.";
            }
        };


        // ---------------------------------------------
        // CLEANUP
        // ---------------------------------------------

        return () => {

            if (recognition) {

                recognition.onresult = null;

                recognition.onend = null;

                recognition.onerror = null;

                try {
                    recognition.stop();
                } catch (e) {}
            }
        };
    }
    """
)


def voice_input_test():
    """
    🎙️ Voice input component.

    The browser listens to the user's speech and sends
    the completed sentence back to Python.

    The actual Gemini conversation is NOT changed here.
    """

    result = VOICE_INPUT_COMPONENT(
        key="nature_voice_input",
        on_speech_change=lambda: None
    )

    voice_text = getattr(
        result,
        "speech",
        None
    )

    return voice_text
# =========================================================
# GOGGY & TITLI AI — DIRECT GEMINI CONNECTION
# Replaces only ask_character_ai(); keeps the rest of app.py
# =========================================================

def ask_character_ai(
    character,
    user_message,
    conversation_history,
    image_bytes=None
):
    if gemini_client is None:
        error = (
            GEMINI_SETUP_ERROR
            or "Gemini client is unavailable. Check GEMINI_API_KEY."
        )
        st.session_state["character_ai_error"] = error
        print("[Goggy & Titli] " + error)
        return None

    # Character personality
    if character == "titli":
        personality = """
You are Titli, a friendly, playful, curious young female companion.
Be warm, expressive, natural, and occasionally playful.
Help with all subjects: education, history, geography, maths,
science, writing, technology, everyday questions, and nature.
Explain difficult topics clearly and correct mistakes gently.
"""
    else:
        personality = """
You are Gogy, a friendly, curious, intelligent young male companion.
Be warm, conversational, playful, and a little more mature than Titli.
Help with all subjects: education, history, geography, maths,
science, writing, technology, everyday questions, and nature.
Explain difficult topics clearly and correct mistakes gently.
"""

    # Build conversation context
    history_lines = []
    for item in conversation_history[-20:]:
        role = item.get("role", "")
        text = str(item.get("content", "")).strip()

        if not text:
            continue

        if role == "user":
            history_lines.append("User: " + text)
        elif role == "assistant":
            history_lines.append(character.capitalize() + ": " + text)

    prompt = f"""
{personality}

You are part of Nature Encyclopedia AI.
Answer the user's actual question accurately and naturally.
You can discuss any subject, not just nature.
For maths, show the working when useful.
For an uploaded photo, inspect what is actually visible.
Do not invent details that cannot be seen.
# LANGUAGE RULES — HINDI AND INDIAN ENGLISH
# Detect the language of the user's latest message.
# Hindi written in Devanagari or Roman Hindi should receive a
# natural Hindi reply. Prefer Devanagari Hindi unless requested otherwise.
# English questions should receive natural English replies.
# Do not unnecessarily mix Hindi and English.
# Keep these language rules for BOTH Goggy and Titli.
# The reply language also determines the spoken language.
LANGUAGE RULES:
- If the user writes in Hindi, reply in natural Hindi.
- If the user writes Hindi using English letters
  (Roman Hindi/Hinglish), understand it as Hindi and reply in Hindi.
- If the user writes in English, reply in English.
- Follow an explicit request to use a different language.
- For Hindi answers, use Devanagari script by default.
- Keep the language consistent throughout the answer.


Do not mention APIs, models, or technical errors.

Previous conversation:
{chr(10).join(history_lines)}

Current message:
{user_message}

Reply as {character.capitalize()}.
"""

    # Prepare the uploaded image, if present
    contents = [prompt]

    if image_bytes:
        try:
            image = Image.open(BytesIO(image_bytes)).convert("RGB")
            image.thumbnail((1600, 1600))
            contents.append(image)
        except Exception as exc:
            error = (
                f"Could not read uploaded image: "
                f"{type(exc).__name__}: {exc}"
            )
            st.session_state["character_ai_error"] = error
            print("[Goggy & Titli] " + error)
            return "I couldn't read that photo. Please upload it again."

    # Try available Gemini models without Google Search tools
    models_to_try = list(dict.fromkeys(
        GEMINI_MODELS + [
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
        ]
    ))

    errors = []

    for model_name in models_to_try:
        try:
            response = gemini_client.models.generate_content(
                model=model_name,
                contents=contents,
            )

            answer = (response.text or "").strip()

            if answer:
                st.session_state["character_ai_error"] = None
                st.session_state["character_ai_model_used"] = model_name
                print(
                    f"[Goggy & Titli] Reply generated using {model_name}"
                )
                return answer

            errors.append(f"{model_name}: empty response")

        except Exception as exc:
            error = f"{model_name}: {type(exc).__name__}: {exc}"
            errors.append(error)
            print("[Goggy & Titli] Gemini attempt failed: " + error)

    diagnostic = "All Gemini models failed:\n" + "\n".join(errors)
    st.session_state["character_ai_error"] = diagnostic
    print("[Goggy & Titli] " + diagnostic)
    return None# =========================================================
# CONVERSATION PAGE — MODULAR, RETRY-SAFE VERSION
# =========================================================

def show_conversation():
    # -----------------------------------------------------
    # 1. Resolve the active character safely
    # Define a safe display name immediately so no UI line can
    # reference character_name before it has been assigned.
    # -----------------------------------------------------
    character = st.session_state.get("active_character", "gogy")
    if character not in ("gogy", "titli"):
        character = "gogy"
    st.session_state.active_character = character
    character_name = "Titli" if character == "titli" else "Gogy"
    character_icon = "👧🦋" if character == "titli" else "👦"
    greeting = (
        "Ooooh! Hiii! I'm Titli! 🦋\n\nWhat do you want to discover?"
        if character == "titli"
        else "Hiii! I'm Gogy! 👋\n\nWhat are you curious about?"
    )

    # Keep history and retry state separate for each character.
    conversation_key = f"{character}_conversation"
    pending_key = f"{character}_pending_retry_message"

    if conversation_key not in st.session_state:
        st.session_state[conversation_key] = []
    if pending_key not in st.session_state:
        st.session_state[pending_key] = None

    conversation_history = st.session_state[conversation_key]

    # Process chat UI actions BEFORE creating widgets. Streamlit forbids
    # changing a widget's keyed state after that widget has been rendered.
    action_key = f"_pending_chat_action_{character}"
    pending_action = st.session_state.pop(action_key, None)
    if pending_action:
        action_type = pending_action.get("type")
        title_key = f"chat_title_{character}"
        if action_type == "load":
            selected_chat = pending_action["chat"]
            st.session_state[conversation_key] = selected_chat.get("messages", [])
            st.session_state.current_chat_ids[character] = selected_chat.get("chat_id")
            st.session_state[title_key] = selected_chat.get("title", "")
            st.session_state[pending_key] = None
        elif action_type == "new":
            st.session_state[conversation_key] = []
            st.session_state.current_chat_ids[character] = None
            st.session_state[title_key] = ""
            st.session_state[pending_key] = None
            st.session_state[f"keep_blank_chat_{character}"] = True
        elif action_type == "rename":
            st.session_state[title_key] = pending_action.get("title", "")
        elif action_type == "deleted_current":
            st.session_state[conversation_key] = []
            st.session_state.current_chat_ids[character] = None
            st.session_state[title_key] = ""
            st.session_state[pending_key] = None
            st.session_state[f"keep_blank_chat_{character}"] = True

    conversation_history = st.session_state[conversation_key]

    # On reopening the app, restore the most recently saved conversation.
    # The New Chat button opts out so it remains a genuinely blank chat.
    keep_blank_key = f"keep_blank_chat_{character}"
    if (
        not conversation_history
        and not st.session_state.current_chat_ids.get(character)
        and not st.session_state.get(keep_blank_key, False)
    ):
        restored_chats, restore_error = get_saved_chats(character)
        if restored_chats:
            latest_chat = restored_chats[0]
            st.session_state[conversation_key] = latest_chat.get("messages", [])
            st.session_state.current_chat_ids[character] = latest_chat.get("chat_id")
            st.session_state[f"chat_title_{character}"] = latest_chat.get("title", "")
            conversation_history = st.session_state[conversation_key]

    # Character display details were assigned safely at the top of this function.

    # -----------------------------------------------------
    # 3. Navigation and character header
    # -----------------------------------------------------
    if st.button("← Home", key="conversation_home"):
        st.session_state.page = "home"
        st.rerun()

    st.title(f"{character_icon} Talk to {character_name}")
    st.caption(f"Talk to {character_name} about anything.")
    if st.button(f"🗣️ Speak with {character_name} in a 🌌 voice space", key=f"open_voice_space_{character}", use_container_width=True):
        st.session_state.page = "voice"
        st.session_state.active_character = character
        st.rerun()# -----------------------------------------------------
    # 3A. SAVED CHAT HISTORY — SEARCH, LOAD, RENAME, SAVE, DELETE
    # -----------------------------------------------------
    with st.expander("🗂️ Chat History / Save / Rename / Delete", expanded=True):
        title_key = f"chat_title_{character}"
        if title_key not in st.session_state:
            st.session_state[title_key] = ""

        st.text_input(
            "Session file name",
            key=title_key,
            placeholder="Example: Chat on dog",
            help="Choose a name before saving. You can rename it later."
        )
        save_col, new_col = st.columns(2)
        with save_col:
            if st.button("💾 Save this entire chat", key=f"save_chat_{character}", use_container_width=True):
                ok, saved_id, error = save_chat_to_supabase(
                    character, conversation_history,
                    st.session_state.current_chat_ids.get(character),
                    st.session_state.get(title_key, "").strip() or None
                )
                if ok:
                    st.session_state.current_chat_ids[character] = saved_id
                    st.success("Entire conversation saved.")
                    st.rerun()
                else:
                    st.error("Could not save chat: " + str(error))
        with new_col:
            if st.button("➕ New chat", key=f"new_chat_{character}", use_container_width=True):
                st.session_state[action_key] = {"type": "new"}
                st.rerun()

        saved_chats, history_error = get_saved_chats(character)
        if history_error:
            st.warning("Chat history is unavailable: " + str(history_error))
        elif not saved_chats:
            st.caption("No saved chats for this character yet. Send messages, give the session a name, then save it.")
        else:
            search_term = st.text_input(
                "🔎 Search saved sessions by name or message",
                key=f"search_saved_chats_{character}",
                placeholder="Example: Chat on dog"
            ).strip().casefold()
            filtered_chats = [
                item for item in saved_chats
                if not search_term
                or search_term in str(item.get("title", "")).casefold()
                or any(search_term in str(m.get("content", "")).casefold() for m in item.get("messages", []))
            ]
            if not filtered_chats:
                st.info("No saved sessions match that search.")
            else:
                chat_labels = {
                    f"{item['title']} · {item['updated_at'].strftime('%d %b %Y %H:%M') if item['updated_at'] else 'Saved'} · {item['chat_id'][:8]}": item
                    for item in filtered_chats
                }
                selected_label = st.selectbox(
                    f"Saved sessions ({len(filtered_chats)})",
                    list(chat_labels.keys()),
                    key=f"saved_chat_select_{character}"
                )
                selected_chat = chat_labels[selected_label]
                rename_key = f"rename_title_{character}"
                st.text_input("Rename selected session", value=selected_chat["title"], key=rename_key)
                load_col, rename_col, delete_col = st.columns(3)
                with load_col:
                    if st.button("📂 Open chat", key=f"load_chat_{character}", use_container_width=True):
                        st.session_state[action_key] = {"type": "load", "chat": selected_chat}
                        st.rerun()
                with rename_col:
                    if st.button("✏️ Rename", key=f"rename_chat_{character}", use_container_width=True):
                        ok, renamed_id, error = save_chat_to_supabase(
                            character, selected_chat["messages"], selected_chat["chat_id"],
                            st.session_state.get(rename_key, "").strip()
                        )
                        if ok:
                            if st.session_state.current_chat_ids.get(character) == selected_chat["chat_id"]:
                                st.session_state[action_key] = {
                                    "type": "rename",
                                    "title": st.session_state.get(rename_key, "").strip()
                                }
                            st.success("Session renamed.")
                            st.rerun()
                        else:
                            st.error("Could not rename session: " + str(error))
                with delete_col:
                    if st.button("🗑️ Delete", key=f"delete_chat_{character}", use_container_width=True):
                        ok, error = delete_chat_from_supabase(selected_chat["chat_id"])
                        if ok:
                            if st.session_state.current_chat_ids.get(character) == selected_chat["chat_id"]:
                                st.session_state[action_key] = {"type": "deleted_current"}
                            st.success("Session deleted.")
                            st.rerun()
                        else:
                            st.error("Could not delete chat: " + str(error))# -----------------------------------------------------
    # 4. Render greeting and existing conversation
    # -----------------------------------------------------
    if not conversation_history:
        with st.chat_message("assistant"):
            st.write(greeting)

    for message in conversation_history:
        role = message.get("role", "assistant")
        content = message.get("content", "")
        if role not in ("user", "assistant"):
            role = "assistant"
        with st.chat_message(role):
            st.write(content)
            saved_image = decode_chat_image(message.get("image_base64"))
            if saved_image:
                st.image(saved_image, caption="Photo attached to this message", use_container_width=True)

    # -----------------------------------------------------
    # 5. Text and microphone input
    # -----------------------------------------------------
    # Photo upload for questions, worksheets, maps, objects, diagrams, etc.
    uploader_version_key = f"{character}_image_uploader_version"
    if uploader_version_key not in st.session_state:
        st.session_state[uploader_version_key] = 0
    attached_image_key = f"{character}_attached_image_bytes"
    uploaded_chat_image = st.file_uploader(
        "📷 Attach a photo (math question, worksheet, map, object, etc.)",
        type=["jpg", "jpeg", "png", "webp"],
        key=f"{character}_chat_image_{st.session_state[uploader_version_key]}",
        help="Upload a clear photo, then type what you want Gogy/Titli to do with it."
    )
    if uploaded_chat_image is not None:
        st.session_state[attached_image_key] = uploaded_chat_image.getvalue()
    image_preview_bytes = st.session_state.get(attached_image_key)
    if image_preview_bytes:
        st.image(image_preview_bytes, caption="Photo ready to send", use_container_width=True)

    voice_text = voice_input_test()
    user_message = st.chat_input(
        f"Ask {character_name} anything — or ask about your photo...",
        key=f"{character}_chat_input"
    )

    # Use recognised speech only when no typed message exists.
    if not user_message and voice_text:
        user_message = str(voice_text).strip() or None

    # -----------------------------------------------------
    # 6. Process a new message
    # -----------------------------------------------------
    if user_message:
        user_message = user_message.strip()
        if user_message:
            image_bytes_for_message = st.session_state.get(attached_image_key)
            image_base64_for_message = encode_chat_image(image_bytes_for_message)
            user_message_record = {
                "role": "user",
                "content": user_message
            }
            if image_base64_for_message:
                user_message_record["image_base64"] = image_base64_for_message
                user_message_record["image_mime"] = "image/jpeg"
            conversation_history.append(user_message_record)
            st.session_state[pending_key] = user_message

            with st.chat_message("user"):
                st.write(user_message)
                if image_bytes_for_message:
                    st.image(image_bytes_for_message, caption="Attached photo", use_container_width=True)

            # Exclude the latest message from history because
            # ask_character_ai receives it separately.
            history_for_prompt = conversation_history[:-1]

            answer = None
            with st.chat_message("assistant"):
                with st.spinner(f"{character_name} is thinking..."):
                    try:
                        answer = ask_character_ai(
                            character,
                            user_message,
                            history_for_prompt,
                            image_bytes=image_bytes_for_message
                        )
                    except Exception as exc:
                        st.session_state["character_ai_error"] = str(exc)
                        answer = None

                if not answer:
                    st.warning(
                        f"I couldn't connect to {character_name} right now. "
                        "Your message is saved; use the Retry button below."
                    )
                else:
                    answer = str(answer).strip()
                    st.write(answer)
                    conversation_history.append({
                        "role": "assistant",
                        "content": answer
                    })
                    st.session_state[pending_key] = None

                    # If this conversation was already saved, update that same session
                    # so the entire new exchange persists without creating a one-message file.
                    active_saved_id = st.session_state.current_chat_ids.get(character)
                    if active_saved_id:
                        auto_ok, auto_saved_id, auto_error = save_chat_to_supabase(
                            character, conversation_history, active_saved_id,
                            st.session_state.get(f"chat_title_{character}", "").strip() or None
                        )
                        if auto_ok:
                            # Keep the latest ID if the saver had to replace a stale/conflicting ID.
                            st.session_state.current_chat_ids[character] = auto_saved_id
                        else:
                            st.warning("Reply received, but updating the saved session failed: " + str(auto_error))

                    # FREE BUILT-IN SPEECH: no ElevenLabs credits or API call.
                    if st.session_state.get("audio_enabled", True):
                        speak_character_text(character, answer)

            # A sent message starts a real chat, so New Chat no longer blocks restore.
            st.session_state[keep_blank_key] = False
            # Reset the uploader widget for the next message.
            st.session_state[attached_image_key] = None
            st.session_state[uploader_version_key] += 1

            # Auto-save every new message/answer so a completed turn is persisted.
            if conversation_history:
                saved_ok, saved_id, saved_error = save_chat_to_supabase(
                    character, conversation_history,
                    st.session_state.current_chat_ids.get(character),
                    st.session_state.get(f"chat_title_{character}", "").strip() or None
                )
                if saved_ok:
                    st.session_state.current_chat_ids[character] = saved_id
                else:
                    st.warning("Chat is only in this session; Supabase save failed: " + str(saved_error))

    # -----------------------------------------------------
    # 7. Retry the last failed message for this character
    # -----------------------------------------------------
    pending_message = st.session_state.get(pending_key)

    if pending_message:
        st.info(
            f"Your message to {character_name} is saved. "
            "You can retry it without typing it again."
        )

        if st.button(
            f"🔄 Retry message — {character_name}",
            key=f"retry_{character}"
        ):
            # Do not append the user message a second time.
            history_for_prompt = conversation_history
            if (
                history_for_prompt
                and history_for_prompt[-1].get("role") == "user"
                and history_for_prompt[-1].get("content") == pending_message
            ):
                history_for_prompt = history_for_prompt[:-1]

            retry_answer = None
            pending_image_bytes = None
            for saved_message in reversed(conversation_history):
                if (
                    saved_message.get("role") == "user"
                    and saved_message.get("content") == pending_message
                ):
                    pending_image_bytes = decode_chat_image(saved_message.get("image_base64"))
                    break

            with st.chat_message("assistant"):
                with st.spinner(f"{character_name} is trying again..."):
                    try:
                        retry_answer = ask_character_ai(
                            character,
                            pending_message,
                            history_for_prompt,
                            image_bytes=pending_image_bytes
                        )
                    except Exception as exc:
                        st.session_state["character_ai_error"] = str(exc)
                        retry_answer = None

                if not retry_answer:
                    st.warning(
                        f"{character_name} still couldn't answer. "
                        "Your message is still saved. Please retry again."
                    )
                else:
                    retry_answer = str(retry_answer).strip()
                    st.write(retry_answer)
                    conversation_history.append({
                        "role": "assistant",
                        "content": retry_answer
                    })
                    st.session_state[pending_key] = None
                    st.session_state[keep_blank_key] = False

                    # FREE BUILT-IN SPEECH: no ElevenLabs credits or API call.
                    if st.session_state.get("audio_enabled", True):
                        speak_character_text(character, retry_answer)

                    # Persist the retry answer to Supabase before refreshing.
                    saved_ok, saved_id, saved_error = save_chat_to_supabase(
                        character, conversation_history,
                        st.session_state.current_chat_ids.get(character)
                    )
                    if saved_ok:
                        st.session_state.current_chat_ids[character] = saved_id
                    else:
                        st.warning("Retry worked, but Supabase save failed: " + str(saved_error))

                    # Refresh to render the saved answer in chat history.
                    st.rerun()# -----------------------------------------------------
    # 8. Voice settings
    # -----------------------------------------------------
    st.divider()
    st.subheader("🔊 Voice")
    st.session_state.audio_enabled = st.toggle(
        "Enable character voice",
        value=st.session_state.get("audio_enabled", True),
        key="character_audio_toggle"
    )

    if st.session_state.audio_enabled:
        st.caption(f"🔊 {character_name} will speak their replies.")
    else:
        st.caption("🔇 Character voice is turned off.")

 # =========================================================
# =========================================================
# VOICE-ONLY SPACE — animated avatar + spoken conversation
# Replies are played as audio and are not printed as chat text.
# =========================================================
def show_voice_space():
    character = st.session_state.get("active_character", "gogy")
    if character not in ("gogy", "titli"):
        character = "gogy"
    character_name = "Titli" if character == "titli" else "Gogy"
    emoji = "🙋🏼‍♀️" if character == "titli" else "🙋🏻‍♂️"
    conversation_key = f"{character}_conversation"
    if conversation_key not in st.session_state:
        st.session_state[conversation_key] = []

    if st.button("← Back to chat", key="back_from_voice_space"):
        st.session_state.page = "conversation"
        st.rerun()

    st.title(f"🌌 Voice Space with {character_name}")
    st.caption("Speak using the microphone. Replies are spoken aloud; text replies are hidden.")
    st.markdown("""
    <style>
    .voice-stage { min-height: 250px; border-radius: 28px; padding: 24px 12px;
        text-align:center; background: radial-gradient(circle at 50% 35%, #45317d, #15152e 65%, #080814);
        color:white; overflow:hidden; }
    .voice-avatar { font-size: 100px; display:inline-block; animation: bob 1.2s ease-in-out infinite; }
    .voice-stars { font-size: 24px; letter-spacing: 14px; animation: twinkle 1.5s ease-in-out infinite alternate; }
    .voice-speaking { font-size: 15px; margin-top: 8px; opacity:.9; }
    @keyframes bob { 0%,100% { transform:translateY(0) rotate(-3deg); } 50% { transform:translateY(-12px) rotate(3deg); } }
    @keyframes twinkle { from { opacity:.35; } to { opacity:1; } }
    </style>
    """, unsafe_allow_html=True)
    st.markdown(
        f'<div class="voice-stage"><div class="voice-stars">✦ · ✧ · ✦</div>'
        f'<div class="voice-avatar">{emoji}</div>'
        f'<h2 style="color:white">{character_name}</h2>'
        f'<div class="voice-speaking">✨ Listening for your question… ✨</div></div>',
        unsafe_allow_html=True
    )

    greeting_key = f"voice_greeting_done_{character}"
    if not st.session_state.get(greeting_key):
        greeting = (
            "Ooooh, hiii! I'm Titli! What would you like to discover today?"
            if character == "titli"
            else "Hiii! I'm Gogy! What would you like to know today?"
        )
        # FREE BUILT-IN SPEECH: no ElevenLabs credits or API call.
        speak_character_text(character, greeting)
        st.session_state[greeting_key] = True

    voice_text = voice_input_test()
    if voice_text and str(voice_text).strip():
        user_message = str(voice_text).strip()
        history = st.session_state[conversation_key]
        history.append({"role": "user", "content": user_message})
        with st.spinner(f"{character_name} is thinking…"):
            answer = ask_character_ai(character, user_message, history[:-1])
        if answer:
            answer = str(answer).strip()
            history.append({"role": "assistant", "content": answer})
            # FREE BUILT-IN SPEECH: no ElevenLabs credits or API call.
            speak_character_text(character, answer)
            active_id = st.session_state.current_chat_ids.get(character)
            if active_id:
                ok, voice_saved_id, err = save_chat_to_supabase(
                    character, history, active_id,
                    st.session_state.get(f"chat_title_{character}", "").strip() or None
                )
                if ok:
                    st.session_state.current_chat_ids[character] = voice_saved_id
                else:
                    st.warning("Voice reply was not saved to Supabase: " + str(err))
        else:
            st.warning(f"{character_name} couldn't answer right now. Please try again.")

    st.caption("Tip: tap the microphone, allow browser microphone access, and speak clearly.")
    if st.button("💬 Return to text chat", key="return_to_text_chat", use_container_width=True):
        st.session_state.page = "conversation"
        st.rerun()# SEARCH PAGE
# =========================================================

def show_search():

    if st.button("← Home"):

        st.session_state.page = "home"

        st.rerun()

    st.title(
        "🌿 Explore Flora & Fauna"
    )

    st.write(
        "Search for an animal or plant "
        "by common or scientific name."
    )

    # =====================================================
    # SEARCH FORM
    # =====================================================

    with st.form(
        "nature_search_form"
    ):

        search_name = st.text_input(
            "Search organism",
            value=st.session_state.search_name,
            placeholder=(
                "Example: Tiger, Rabbit, "
                "Mango, Neem..."
            )
        )

        submitted = st.form_submit_button(
            "🔎 Search",
            use_container_width=True
        )

    # =====================================================
    # SEARCH
    # =====================================================

    if submitted:

        if not search_name.strip():

            st.warning(
                "Please enter an organism name."
            )

            return

        st.session_state.search_name = (
            search_name.strip()
        )

        with st.spinner(
            "Finding this organism..."
        ):

            taxon = search_taxon_cached(
                search_name.strip()
            )

            if (
                taxon
                and not taxon.get("error")
            ):

                taxon_id = taxon.get("id")

                observations = []

                if taxon_id:

                    observations = (
                        get_observations_cached(
                            taxon_id
                        )
                    )

                st.session_state.selected_taxon = (
                    taxon
                )

                st.session_state.selected_observations = (
                    observations
                )

                st.rerun()

            elif (
                taxon
                and taxon.get("error")
            ):

                st.error(
                    "iNaturalist error: "
                    + str(taxon["error"])
                )

            else:

                st.warning(
                    "No matching organism was found."
)# =====================================================
    # SHOW SPECIES
    # =====================================================

    if st.session_state.selected_taxon:

        show_species_page(
            st.session_state.selected_taxon,
            st.session_state.selected_observations
        )


# =========================================================
# PHOTO IDENTIFICATION PAGE
# =========================================================

def show_identify():

    if st.button("← Home"):

        st.session_state.page = "home"

        st.rerun()

    st.title(
        "📷 Identify an Animal or Plant"
    )

    st.write(
        "Upload a photograph and AI will "
        "try to identify the organism."
    )

        # =====================================================
    # 📷 PHOTO INPUT — GALLERY + CAMERA
    # =====================================================

    # 📁 Option 1: Choose an existing photograph
    uploaded_file = st.file_uploader(
        "📁 Choose a photograph from your gallery",
        type=[
            "jpg",
            "jpeg",
            "png",
            "webp"
        ]
    )

    # 📸 Option 2: Take a new photograph with the camera
    camera_photo = st.camera_input(
        "📸 Or take a photograph"
    )

    # Use whichever option the user selected
    selected_photo = camera_photo or uploaded_file
    # =====================================================
    # PROCESS SELECTED PHOTO
    # =====================================================

    if selected_photo:

        image_bytes = selected_photo.getvalue()

        image_hash = hashlib.sha256(
            image_bytes
        ).hexdigest()

         
        # =================================================
        # NEW IMAGE
        # =================================================

        if (
            st.session_state.image_hash
            != image_hash
        ):

            st.session_state.image_bytes = (
                image_bytes
            )

            st.session_state.image_hash = (
                image_hash
            )

            st.session_state.ai_result = None

            st.session_state.ai_model_used = None

            st.session_state.selected_taxon = None

            st.session_state.selected_observations = []

    # =====================================================
    # DISPLAY IMAGE
    # =====================================================

    if st.session_state.image_bytes:

        image = Image.open(
            BytesIO(
                st.session_state.image_bytes
            )
        )

        st.image(
            image,
            caption="Uploaded Photograph",
            use_container_width=True
        )

        # =================================================
        # IDENTIFY
        # =================================================

        if st.session_state.ai_result is None:

            if st.button(
                "🔍 Identify",
                type="primary",
                use_container_width=True
            ):

                with st.spinner(
                    "AI is examining the photograph..."
                ):

                    result = (
                        identify_organism_cached(
                            st.session_state.image_bytes,
                            st.session_state.image_hash
                        )
                    )

                if result["success"]:

                    st.session_state.ai_result = (
                        result["result"]
                    )

                    st.session_state.ai_model_used = (
                        result["model"]
                    )

                    st.rerun()

                else:

                    st.error(
                        "The AI service is "
                        "temporarily unavailable."
                    )

                    with st.expander(
                        "Technical details"
                    ):

                        st.code(
                            result["error"]
    )
    # =================================================
        # AI RESULT
        # =================================================

        if st.session_state.ai_result:

            result = (
                st.session_state.ai_result
            )

            organism_type = (
                result.get(
                    "type",
                    "organism"
                )
            )

            common_name = (
                result.get(
                    "common_name",
                    "Unknown"
                )
            )

            scientific_name = (
                result.get(
                    "scientific_name",
                    ""
                )
            )

            confidence = (
                result.get(
                    "confidence",
                    0
                )
            )

            reason = (
                result.get(
                    "reason",
                    ""
                )
            )

            if (
                organism_type.lower()
                == "plant"
            ):

                st.success(
                    "🌱 Identified: **"
                    + common_name
                    + "**"
                )

            else:

                st.success(
                    "🐾 Identified: **"
                    + common_name
                    + "**"
                )

            st.metric(
                "AI Confidence",
                str(confidence) + "%"
            )

            if scientific_name:

                st.write(
                    "**Scientific name:** *"
                    + scientific_name
                    + "*"
                )

            if reason:

                st.write(
                    "**Why:** "
                    + reason
                )

            if st.session_state.ai_model_used:

                st.caption(
                    "AI model: "
                    + st.session_state.ai_model_used
                )

            # =============================================
            # FIND iNATURALIST SPECIES
            # =============================================

            if (
                st.session_state.selected_taxon
                is None
            ):

                if st.button(
                    "🌍 Find Species Information",
                    type="primary",
                    use_container_width=True
                ):

                    with st.spinner(
                        "Finding biodiversity information..."
                    ):

                        if scientific_name:

                            taxon = (
                                search_taxon_cached(
                                    scientific_name
                                )
                            )

                        else:

                            taxon = (
                                search_taxon_cached(
                                    common_name
                                )
                            )

                        if (
                            taxon
                            and not taxon.get("error")
                        ):

                            taxon_id = (
                                taxon.get("id")
                            )

                            observations = []

                            if taxon_id:

                                observations = (
                                    get_observations_cached(
                                        taxon_id
                                    )
                                )

                            st.session_state.selected_taxon = (
                                taxon
                            )

                            st.session_state.selected_observations = (
                                observations
                            )

                            st.rerun()

                        else:

                            st.warning(
                                "The organism was identified, "
                                "but no matching iNaturalist "
                                "taxon was found."
                            )

            # =============================================
            # SPECIES PAGE
            # =============================================

            if st.session_state.selected_taxon:

                show_species_page(
                    st.session_state.selected_taxon,
                    st.session_state.selected_observations,
                    ai_result=result
                )

    else:

        st.info(
            "📷 Upload a photograph to begin."
        )


# =========================================================
# GLOBAL SIDEBAR NAVIGATION
# Add future navigation items to NAV_ITEMS below.
# =========================================================

def show_sidebar():
    nav_items = [
        ("🏠 Home", "home"),
        ("🧒 Talk to Gogy", "gogy"),
        ("🦋 Talk to Titli", "titli"),
        ("🔎 Search Organism", "search"),
        ("📸 Identify from Photo", "identify"),
    ]

    with st.sidebar:
        st.title("🌍 Nature AI")
        st.caption("Where would you like to go?")
        st.divider()

        for label, destination in nav_items:
            if st.button(
                label,
                key=f"nav_{destination}",
                use_container_width=True
            ):
                if destination in ("gogy", "titli"):
                    st.session_state.active_character = destination
                    st.session_state.page = "conversation"
                else:
                    st.session_state.page = destination

                st.rerun()
            # =========================================================
# SHOW SIDEBAR BEFORE OPENING ANY PAGE
# =========================================================

show_sidebar()

# ============================================================
# APP ROUTER — CENTRAL PLACE TO REGISTER NEW PAGES
# To add a page later:
# 1. Define the new page function above this router.
# 2. Add its page key and function to PAGE_ROUTES.
# ============================================================

PAGE_ROUTES = {
    "home": show_home,
    "search": show_search,
    "identify": show_identify,
    "conversation": show_conversation,
    "gogy": show_conversation,
    "titli": show_conversation,
    "voice": show_voice_space,
}

# ============================================================
# OPEN THE SELECTED PAGE
# ============================================================

current_page = st.session_state.get("page", "home")

# Fall back safely if the selected page key is unknown.

# ============================================================
# ROUTER SAFETY — FALL BACK TO HOME FOR UNKNOWN PAGE KEYS
# ============================================================

if current_page not in PAGE_ROUTES:
    st.session_state.page = "home"
    current_page = "home"

# Get the selected page function safely.
page_function = PAGE_ROUTES.get(current_page, show_home)

# Render the selected page.
page_function()
