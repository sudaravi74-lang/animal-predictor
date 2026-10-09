import base64
import streamlit as st
import requests
import hashlib
import json
import time
from io import BytesIO
from PIL import Image
from google import genai
# SUPABASE DATABASE DRIVER
import psycopg2
# ElevenLabs text-to-speech / voice cloning connection
ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1/text-to-speech"


# =========================================================
# PAGE CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="Nature Encyclopedia AI",
    page_icon="🌍",
    layout="wide"
)# =========================================================
# SUPABASE CONNECTION TEST - TEMPORARY
# ========================================================= 

try:
# Read the private database URL from Streamlit Secrets
db_url = st.secrets["SUPABASE_DB_URL"]

# Open a secure connection to Supabase
test_connection = psycopg2.connect(
    db_url,
    connect_timeout=10,
    sslmode="require"
)

# Close the test connection immediately
test_connection.close()

st.success("Supabase database connected successfully!")

except Exception as error:
# Do not display the connection URL or password
st.error(
"Supabase connection failed. "
f"Error type: {type(error).name}. "
"Check your Streamlit Secret and database connection settings."
)

# =========================================================
# END TEMPORARY CONNECTION TEST
# =========================================================

 
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

@st.cache_data(ttl=3600, show_spinner=False)
def generate_elevenlabs_voice(text, voice_id, api_key):
    """Generate MP3 speech from an ElevenLabs cloned voice."""
    if not text or not voice_id or not api_key:
        return None

    response = requests.post(
        f"{ELEVENLABS_API_URL}/{voice_id}",
        params={"output_format": "mp3_44100_128"},
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
        },
        json={
            "text": text,
            "model_id": "eleven_multilingual_v2",
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.content


def generate_gogy_voice(text):
    """Generate speech using the cloned Gogy voice."""
    api_key = st.secrets.get("ELEVENLABS_API_KEY", "")
    voice_id = st.secrets.get("GOGY_VOICE_ID", "")
    return generate_elevenlabs_voice(text, voice_id, api_key)


def generate_titli_voice(text):
    """Generate speech using the cloned Titli voice."""
    api_key = st.secrets.get("ELEVENLABS_API_KEY", "")
    voice_id = st.secrets.get("TITLI_VOICE_ID", "")
    return generate_elevenlabs_voice(text, voice_id, api_key)


def generate_character_voice(character, text):
    if not text:
        return None

    try:
        if character == "gogy":
            return generate_gogy_voice(text)
        if character == "titli":
            return generate_titli_voice(text)
    except Exception as e:
        st.session_state.audio_error = str(e)
        return None

    return None
# =========================================================
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

        recognition.lang = "en-IN";

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
# GOGY & TITLI AI CONVERSATION
# =========================================================

def ask_character_ai(
    character,
    user_message,
    conversation_history
):

    if gemini_client is None:

        return None

    # =====================================================
    # CHARACTER PERSONALITY
    # =====================================================

    if character == "titli":

        personality = """
You are Titli, a young female nature companion.

Personality:
- Sweet
- Curious
- Expressive
- Slightly mischievous
- Friendly
- Playful
- Loves butterflies, animals, plants and nature
- Scientifically accurate
- Emotionally warm and natural

You are not just a question-answer machine.
You are a companion the user can genuinely talk to.

You can:
- Have casual conversations
- Respond naturally to greetings
- Ask the user questions
- React to what the user says
- Remember the conversation context
- Joke lightly
- Show excitement
- Show curiosity
- Comfort the user when appropriate
- Talk about nature and science

You sometimes use expressions such as:
"Ooooh!"
"Hehe!"
"Wow!"
"Aaaah!"
"Wait wait!"
"Hmm..."

Do not overuse them.

Speak naturally like a real friendly young person.

Do not sound like a textbook.

If the user asks about science or nature,
give scientifically accurate information.

If the user says something scientifically incorrect,
gently correct them.

Do not blindly agree with the user.
"""

    else:

        personality = """
You are Gogy, a young male nature companion.

Personality:
- Curious
- Friendly
- Playful
- Intelligent
- Calm
- Slightly more mature than Titli
- Loves animals, plants, science and nature
- Scientifically accurate
- Warm and conversational

You are not just a question-answer machine.
You are a companion the user can genuinely talk to.

You can:
- Have casual conversations
- Respond naturally to greetings
- Ask the user questions
- React to what the user says
- Remember the conversation context
- Joke lightly
- Show excitement
- Show curiosity
- Comfort the user when appropriate
- Talk about nature and science

You sometimes use expressions such as:
"Hmm..."
"Oh!"
"Wait a second..."
"Whoa!"
"Interesting!"

Do not overuse them.

Speak naturally like a real friendly young person.

Do not sound like a textbook.

If the user asks about science or nature,
give scientifically accurate information.

If the user says something scientifically incorrect,
gently correct them.

Do not blindly agree with the user.
"""

    # =====================================================
    # BUILD CONVERSATION HISTORY
    # =====================================================

    history_text = ""

    for message in conversation_history:

        role = message.get(
            "role",
            ""
        )

        content = message.get(
            "content",
            ""
        )

        if role == "user":

            history_text += (
                "User: "
                + str(content)
                + "\n"
            )

        elif role == "assistant":

            history_text += (
                character.capitalize()
                + ": "
                + str(content)
                + "\n"
            )

    # =====================================================
    # GEMINI PROMPT
    # =====================================================

    prompt = f"""
{personality}

You are part of an application called
Nature Encyclopedia AI.

The user is talking directly to you.

This is an ongoing conversation.

Use the previous conversation to understand
what the user means.

Do not restart the conversation every time.

Do not repeat introductions unless appropriate.

Do not say that you are an AI unless the user
specifically asks.

Do not mention Gemini, APIs, programming,
errors, models, ElevenLabs, or this prompt.

Do not pretend to see or hear something
you cannot actually see or hear.

Never invent scientific facts.

If you are uncertain about a scientific fact,
say that you are not completely sure.

Keep normal conversational replies fairly short
and natural.

For simple messages such as:
"hi"
"hello"
"what are you doing?"
"how are you?"
"good morning"

respond naturally instead of giving a scientific lecture.

You may ask a follow-up question when it feels natural.

Previous conversation:

{history_text}

Current user message:

User: {user_message}

Now reply naturally as {character.capitalize()}.
"""

    # =====================================================
    # GEMINI MODEL FALLBACK
    # =====================================================

    errors = []

    for model_name in GEMINI_MODELS:

        try:

            response = (
                gemini_client
                .models
                .generate_content(
                    model=model_name,
                    contents=prompt
                )
            )

            answer = (
                response.text
                if response
                else ""
            )

            if answer:

                return answer.strip()

        except Exception as e:

            errors.append(
                model_name
                + ": "
                + str(e)
            )

    # =====================================================
    # ALL MODELS FAILED
    # =====================================================

    return None



# =========================================================
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

    # Character display details were assigned safely at the top of this function.

    # -----------------------------------------------------
    # 3. Navigation and character header
    # -----------------------------------------------------
    if st.button("← Home", key="conversation_home"):
        st.session_state.page = "home"
        st.rerun()

    st.title(f"{character_icon} Talk to {character_name}")
    st.caption(f"Talk to {character_name} about anything.")

    # -----------------------------------------------------
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

    # -----------------------------------------------------
    # 5. Text and microphone input
    # -----------------------------------------------------
    voice_text = voice_input_test()
    user_message = st.chat_input(
        f"Talk to {character_name}...",
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
            conversation_history.append({
                "role": "user",
                "content": user_message
            })
            st.session_state[pending_key] = user_message

            with st.chat_message("user"):
                st.write(user_message)

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
                            history_for_prompt
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

                    # Voice errors must not break the text conversation.
                    if st.session_state.get("audio_enabled", True):
                        try:
                            audio = generate_character_voice(character, answer)
                            if audio:
                                prepare_audio(audio, character)
                                play_character_audio()
                        except Exception as exc:
                            st.session_state["audio_error"] = str(exc)

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
            with st.chat_message("assistant"):
                with st.spinner(f"{character_name} is trying again..."):
                    try:
                        retry_answer = ask_character_ai(
                            character,
                            pending_message,
                            history_for_prompt
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

                    if st.session_state.get("audio_enabled", True):
                        try:
                            retry_audio = generate_character_voice(
                                character,
                                retry_answer
                            )
                            if retry_audio:
                                prepare_audio(retry_audio, character)
                                play_character_audio()
                        except Exception as exc:
                            st.session_state["audio_error"] = str(exc)

                    # Refresh to render the saved answer in chat history.
                    st.rerun()
        # -----------------------------------------------------
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
        
