import base64
import streamlit as st
import requests
import hashlib
import json
import time
from io import BytesIO
from PIL import Image
from google import genai


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
    "character_conversation": [],
    "voice_enabled": True,
    "audio_enabled": True,
    "last_audio": None,
    "audio_character": None,
    "gogy_expression": "happy",
    "titli_expression": "happy",
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# =========================================================
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


# =========================================================
# iNATURALIST TAXON SEARCH
# =========================================================

@st.cache_data(
    ttl=3600,
    show_spinner=False
)
def search_taxon_cached(search_name):

    try:
        response = requests.get(
            INAT_TAXA_URL,
            params={
                "q": search_name,
                "per_page": 10
            },
            headers=HEADERS,
            timeout=15
        )

        response.raise_for_status()

        results = response.json().get(
            "results",
            []
        )

        if not results:
            return None

        search_lower = (
            search_name.strip().lower()
        )

        # Exact common/scientific name
        for taxon in results:

            common_name = (
                taxon.get(
                    "preferred_common_name"
                )
                or ""
            ).lower()

            scientific_name = (
                taxon.get("name")
                or ""
            ).lower()

            if (
                common_name == search_lower
                or scientific_name == search_lower
            ):
                return taxon

        # Otherwise use first result
        return results[0]

    except Exception as e:

        return {
            "error": str(e)
        }


# =========================================================
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

try:

    GEMINI_API_KEY = st.secrets[
        "GEMINI_API_KEY"
    ]

    gemini_client = genai.Client(
        api_key=GEMINI_API_KEY
    )

except Exception:

    gemini_client = None


# =========================================================
# GEMINI MODELS
# =========================================================

GEMINI_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash"
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
    }


# =========================================================
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

    return "organism"

# =========================================================
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
    )

    # =====================================================
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
            )

    # =====================================================
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

            st.session_state.character_conversation = []

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

            st.session_state.character_conversation = []

            st.session_state.page = "conversation"

            st.rerun()

    st.divider()

    # =====================================================
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
    ) 
# =========================================================
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
# =========================================================

def generate_gogy_voice(text):
    """
    Gogy voice.

    Future:
    Gemini answer
        ↓
    AI Two Finn voice
        ↓
    MP3 bytes
    """

    return None


def generate_titli_voice(text):
    """
    Titli voice.

    Future:
    Gemini answer
        ↓
    SpeechGen selected voice
        ↓
    MP3 bytes
    """

    return None


def generate_character_voice(character, text):

    if not text:
        return None

    if character == "gogy":
        return generate_gogy_voice(text)

    if character == "titli":
        return generate_titli_voice(text)

    return None
# =========================================================
# GOGY & TITLI AI CONVERSATION
# =========================================================

def ask_character_ai(
    character,
    user_message
):

    if gemini_client is None:

        return (
            "I'm sorry! My AI brain isn't connected "
            "right now. Please check the Gemini API key."
        )

    if character == "titli":

        personality = """
You are Titli, a young female nature companion.

Personality:
- Sweet
- Curious
- Expressive
- Slightly mischievous
- Loves animals, plants and nature
- Very friendly
- Scientifically accurate

You sometimes use cute expressions such as:
"Ooooh!"
"Hehe!"
"Aaaah!"
"Wow!"
"Hmph!"
"Wait wait!"

Do not overuse them.

If the user says something scientifically incorrect,
gently correct them.

Do not blindly agree with the user.

Keep answers easy to understand and conversational.
"""

    else:

        personality = """
You are Gogy, a young male nature companion.

Personality:
- Curious
- Friendly
- Playful
- A little more mature and calm than Titli
- Loves explaining nature
- Scientifically accurate

You sometimes use expressions such as:
"Hmm..."
"Oh!"
"Wait a second..."
"Whoa!"
"Interesting!"

Do not overuse them.

If the user says something scientifically incorrect,
gently correct them.

Do not blindly agree with the user.

Keep answers conversational and easy to understand.
"""

    prompt = f"""
{personality}

You are part of an application called
Nature Encyclopedia AI.

The user is talking directly to you.

Answer the user's question naturally.

User message:
{user_message}

Important:
- Do not mention that you are an AI unless asked.
- Do not pretend to have seen something you haven't seen.
- Never invent scientific facts.
- If you are uncertain, say so.
- Prefer short, engaging answers.
"""

    try:

        response = (
            gemini_client
            .models
            .generate_content(
                model=GEMINI_MODELS[0],
                contents=prompt
            )
        )

        return response.text.strip()

    except Exception as e:

        return (
            "Oops! My brain got a little tangled. 😅\n\n"
            "Please try asking me again."
        )


# =========================================================
# CONVERSATION PAGE
# =========================================================
def show_conversation():

    character = st.session_state.active_character

    if character == "titli":
        character_name = "Titli"
        character_icon = "👧🦋"
        greeting = (
            "Ooooh! Hiii! I'm Titli! 🦋\n\n"
            "What do you want to discover?"
        )
    else:
        character_name = "Gogy"
        character_icon = "🧒"
        greeting = (
            "Hiii! I'm Gogy! 👋\n\n"
            "What are you curious about?"
        )

    # HOME BUTTON
    if st.button("← Home", key="conversation_home"):
        st.session_state.page = "home"
        st.rerun()

    # CHARACTER TITLE
    st.title(character_icon + " Talk to " + character_name)

    st.caption("Ask me anything about nature.")

    # =====================================================
    # INITIAL GREETING
    # =====================================================

    if not st.session_state.character_conversation:

        with st.chat_message("assistant"):
            st.write(greeting)

    # =====================================================
    # PREVIOUS CONVERSATION
    # =====================================================

    for message in st.session_state.character_conversation:

        if message["role"] == "user":

            with st.chat_message("user"):
                st.write(message["content"])

        else:

            with st.chat_message("assistant"):
                st.write(message["content"])

    # =====================================================
    # TEXT INPUT
    # =====================================================

    user_message = st.chat_input(
        "Talk to " + character_name + "..."
    )

    if user_message:

        # Add user message
        st.session_state.character_conversation.append(
            {
                "role": "user",
                "content": user_message
            }
        )

        # Show user message
        with st.chat_message("user"):
            st.write(user_message)

        # =================================================
        # CHARACTER ANSWER
        # =================================================

        with st.chat_message("assistant"):

            with st.spinner(
                character_name + " is thinking..."
            ):

                answer = ask_character_ai(
                    character,
                    user_message
                )

            # Show text answer
            st.write(answer)

            # =================================================
            # AUDIO ARCHITECTURE
            # =================================================

            audio = generate_character_voice(
                character,
                answer
            )

            if audio:

                prepare_audio(
                    audio,
                    character
                )

                play_character_audio()

        # Save assistant answer
        st.session_state.character_conversation.append(
            {
                "role": "assistant",
                "content": answer
            }
        )

    # =====================================================
    # VOICE SETTINGS
    # =====================================================

    st.divider()

    st.subheader("🔊 Voice")

    st.session_state.audio_enabled = st.toggle(
        "Enable character voice",
        value=st.session_state.get(
            "audio_enabled",
            True
        ),
        key="character_audio_toggle"
    )

    if st.session_state.audio_enabled:

        st.caption(
            "🔊 " +
            character_name +
            " will speak when voice generation is connected."
        )

    else:

        st.caption(
            "🔇 Character voice is turned off."
        )
  

    # =====================================================
    # HEADER
    # =====================================================

    if st.button(
        "← Home",
        key="conversation_home"
    ):

        st.session_state.page = "home"

        st.rerun()

    st.title(
        character_icon
        + " Talk to "
        + character_name
    )

    st.caption(
        "Ask me anything about nature."
    )

    # =====================================================
    # INITIAL GREETING
    # =====================================================

    if not st.session_state.character_conversation:

          with st.chat_message("assistant"):

    with st.spinner(character_name + " is thinking..."):

        answer = ask_character_ai(
            character,
            user_message
        )

    st.write(answer)

    # Prepare character voice
    audio = generate_character_voice(
        character,
        answer
    )

    if audio:

        prepare_audio(
            audio,
            character
        )

        play_character_audio()
    # =====================================================
    # PREVIOUS CONVERSATION
    # =====================================================

    for message in (
        st.session_state.character_conversation
    ):

        if message["role"] == "user":

            with st.chat_message(
                "user"
            ):

                st.write(
                    message["content"]
                )

        else:

            with st.chat_message(
                "assistant"
            ):

                st.write(
                    message["content"]
                )

    # =====================================================
    # TEXT INPUT
    # =====================================================

    user_message = st.chat_input(
        "Talk to " + character_name + "..."
    )

    if user_message:

        st.session_state.character_conversation.append(
            {
                "role": "user",
                "content": user_message
            }
        )

        with st.chat_message("user"):

            st.write(user_message)

        with st.chat_message("assistant"):

            with st.spinner(
                character_name
                + " is thinking..."
            ):

                answer = ask_character_ai(
                    character,
                    user_message
                )

            st.write(answer)

        st.session_state.character_conversation.append(
            {
                "role": "assistant",
                "content": answer
            }
        )

    # =====================================================
    # MICROPHONE
    # =====================================================

     st.divider()

st.subheader("🔊 Voice")

st.session_state.audio_enabled = st.toggle(
    "Enable character voice",
    value=st.session_state.get("audio_enabled", True),
    key="character_audio_toggle"
)

if st.session_state.audio_enabled:
    st.caption(
        "🔊 " + character_name + " will speak when voice generation is connected."
    )
else:
    st.caption("🔇 Character voice is turned off.")                   
                 
    # =========================================================
# SEARCH PAGE
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
                )

    # =====================================================
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
    # UPLOAD
    # =====================================================

    uploaded_file = st.file_uploader(
        "Choose a photograph",
        type=[
            "jpg",
            "jpeg",
            "png",
            "webp"
        ]
    )

    if uploaded_file:

        image_bytes = uploaded_file.getvalue()

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
# APP ROUTER
# =========================================================

if st.session_state.page == "home":

    show_home()

elif st.session_state.page == "search":

    show_search()

elif st.session_state.page == "identify":

    show_identify()

elif st.session_state.page == "conversation":

    show_conversation()    

 
     
 
 
                     
 

 
