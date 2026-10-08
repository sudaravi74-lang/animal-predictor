import streamlit as st
import requests
from PIL import Image
from google import genai


# =========================================================
# PAGE SETTINGS
# =========================================================

st.set_page_config(
    page_title="Animal Encyclopedia AI",
    page_icon="🐾",
    layout="wide"
)

st.title("🐾 Animal Encyclopedia AI")

st.write(
    "Identify animals from images or search the biodiversity database."
)


# =========================================================
# GEMINI API
# =========================================================

try:

    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]

    gemini_client = genai.Client(
        api_key=GEMINI_API_KEY
    )

except Exception:

    gemini_client = None


# =========================================================
# iNATURALIST API
# =========================================================

INAT_API = "https://api.inaturalist.org/v1"


# =========================================================
# GEMINI IMAGE IDENTIFICATION
# =========================================================

def identify_animal_with_gemini(image):

    if gemini_client is None:

        return None, (
            "Gemini API key is not configured. "
            "Please add GEMINI_API_KEY to Streamlit Secrets."
        )

    prompt = """
You are an expert wildlife and animal identification assistant.

Analyze the uploaded image carefully.

Identify the animal visible in the image.

Return ONLY valid JSON in this exact structure:

{
  "animal": "common animal name",
  "scientific_name": "scientific name if reasonably identifiable",
  "confidence": 0,
  "reason": "short visual reason"
}

Important rules:

1. Do not force the animal into a predefined list.
2. If it is a rabbit, say rabbit.
3. If it is a horse, say horse.
4. If it is a giraffe, say giraffe.
5. If it is a bird, identify the bird if possible.
6. If species identification is uncertain, give the broader animal
   and use a lower confidence.
7. Never invent a species.
8. Confidence must be a number from 0 to 100.
"""

    try:

        response = gemini_client.models.generate_content(
            model="gemini-3.8-flash",
            contents=[
                prompt,
                image
            ]
        )

        text = response.text.strip()

        # Remove markdown JSON fences if Gemini adds them
        text = text.replace("```json", "")
        text = text.replace("```", "")
        text = text.strip()

        import json

        result = json.loads(text)

        return result, None

    except Exception as e:

        return None, str(e)


# =========================================================
# SEARCH iNATURALIST TAXON
# =========================================================

def search_taxon(animal_name):

    try:

        url = f"{INAT_API}/taxa/autocomplete"

        params = {
            "q": animal_name,
            "per_page": 5
        }

        response = requests.get(
            url,
            params=params,
            timeout=15
        )

        if response.status_code != 200:
            return None

        data = response.json()

        results = data.get(
            "results",
            []
        )

        if not results:
            return None

        # Prefer an animal result where possible
        for result in results:

            iconic_taxon = result.get(
                "iconic_taxon_name"
            )

            if iconic_taxon in [
                "Mammalia",
                "Aves",
                "Reptilia",
                "Amphibia",
                "Actinopterygii",
                "Insecta",
                "Arachnida",
                "Mollusca"
            ]:

                return result

        return results[0]

    except Exception:

        return None


# =========================================================
# GET iNATURALIST OBSERVATIONS + PHOTOS
# =========================================================

def get_animal_observations(
    taxon_name,
    taxon_id=None,
    number=6
):

    try:

        url = f"{INAT_API}/observations"

        params = {
            "photos": "true",
            "per_page": number,
            "order_by": "votes",
            "order": "desc",
            "quality_grade": "research"
        }

        if taxon_id:

            params["taxon_id"] = taxon_id

        else:

            params["taxon_name"] = taxon_name

        response = requests.get(
            url,
            params=params,
            timeout=20
        )

        if response.status_code != 200:
            return []

        data = response.json()

        return data.get(
            "results",
            []
        )

    except Exception:

        return []


# =========================================================
# GET PHOTO URL
# =========================================================

def get_large_photo_url(photo):

    url = photo.get("url")

    if not url:
        return None

    # iNaturalist photo URLs commonly use
    # /square., /small., /medium., /large., /original.
    # Prefer large for the application.
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
# DISPLAY DATABASE INFORMATION
# =========================================================

def display_animal_data(
    taxon,
    observations
):

    if not taxon:

        st.warning(
            "No matching animal was found in the biodiversity database."
        )

        return


    common_name = taxon.get(
        "preferred_common_name"
    )

    scientific_name = taxon.get(
        "name",
        "Unknown"
    )

    rank = taxon.get(
        "rank",
        "Unknown"
    )

    iconic_taxon = taxon.get(
        "iconic_taxon_name",
        "Unknown"
    )

    st.divider()

    st.header(
        f"🐾 {common_name or scientific_name}"
    )

    st.write(
        f"**Scientific name:** "
        f"{scientific_name}"
    )

    st.write(
        f"**Taxonomic rank:** "
        f"{rank}"
    )

    st.write(
        f"**Major group:** "
        f"{iconic_taxon}"
    )


    # -----------------------------------------------------
    # TAXON PHOTO
    # -----------------------------------------------------

    default_photo = taxon.get(
        "default_photo"
    )

    if default_photo:

        photo_url = get_large_photo_url(
            default_photo
        )

        if photo_url:

            st.image(
                photo_url,
                caption=(
                    common_name
                    or scientific_name
                ),
                use_container_width=True
            )


    # -----------------------------------------------------
    # OBSERVATION PHOTOS
    # -----------------------------------------------------

    if observations:

        st.subheader(
            "📸 More photographs"
        )

        photo_urls = []

        for observation in observations:

            photos = observation.get(
                "photos",
                []
            )

            for photo in photos:

                photo_url = get_large_photo_url(
                    photo
                )

                if photo_url:

                    photo_urls.append(
                        photo_url
                    )

                if len(photo_urls) >= 6:
                    break

            if len(photo_urls) >= 6:
                break


        if photo_urls:

            st.image(
                photo_urls,
                use_container_width=True
            )


    # -----------------------------------------------------
    # SOURCE
    # -----------------------------------------------------

    taxon_id = taxon.get(
        "id"
    )

    if taxon_id:

        st.markdown(
            f"[🌐 View this taxon on iNaturalist]"
            f"(https://www.inaturalist.org/taxa/{taxon_id})"
        )


# =========================================================
# MENU
# =========================================================

option = st.radio(
    "Choose an option:",
    [
        "📷 Identify Animal from Image",
        "🔎 Search Animal"
    ]
)


# =========================================================
# IMAGE IDENTIFICATION
# =========================================================

if option == "📷 Identify Animal from Image":

    st.header(
        "📷 Identify an Animal"
    )

    uploaded_file = st.file_uploader(
        "Upload an animal photograph",
        type=[
            "jpg",
            "jpeg",
            "png",
            "webp"
        ]
    )


    if uploaded_file:

        image = Image.open(
            uploaded_file
        ).convert("RGB")


        st.image(
            image,
            caption="Uploaded Image",
            use_container_width=True
        )


        if st.button(
            "🔍 Identify Animal"
        ):

            with st.spinner(
                "AI is analyzing the animal..."
            ):

                result, error = (
                    identify_animal_with_gemini(
                        image
                    )
                )


            if error:

                st.error(
                    f"AI identification error: {error}"
                )

            elif result:

                animal_name = result.get(
                    "animal",
                    "Unknown"
                )

                scientific_name = result.get(
                    "scientific_name",
                    ""
                )

                confidence = result.get(
                    "confidence",
                    0
                )

                reason = result.get(
                    "reason",
                    ""
                )


                st.success(
                    f"🐾 Identified Animal: "
                    f"**{animal_name.title()}**"
                )

                st.metric(
                    "AI confidence",
                    f"{confidence}%"
                )

                if reason:

                    st.write(
                        f"**Why:** {reason}"
                    )


                # -----------------------------------------
                # SEARCH DATABASE
                # -----------------------------------------

                with st.spinner(
                    "Finding species information and photographs..."
                ):

                    taxon = None

                    # Try scientific name first
                    if scientific_name:

                        taxon = search_taxon(
                            scientific_name
                        )


                    # If scientific name failed,
                    # search common name
                    if not taxon:

                        taxon = search_taxon(
                            animal_name
                        )


                    observations = []

                    if taxon:

                        observations = (
                            get_animal_observations(
                                taxon.get("name"),
                                taxon.get("id"),
                                6
                            )
                        )


                display_animal_data(
                    taxon,
                    observations
                )


# =========================================================
# ANIMAL SEARCH
# =========================================================

elif option == "🔎 Search Animal":

    st.header(
        "🔎 Search the Animal Database"
    )

    search_name = st.text_input(
        "Enter any animal name:",
        placeholder="Example: Snow Leopard"
    )


    if st.button(
        "🔎 Search"
    ):

        if not search_name.strip():

            st.warning(
                "Please enter an animal name."
            )

        else:

            with st.spinner(
                "Searching biodiversity database..."
            ):

                taxon = search_taxon(
                    search_name.strip()
                )


                observations = []

                if taxon:

                    observations = (
                        get_animal_observations(
                            taxon.get("name"),
                            taxon.get("id"),
                            6
                        )
                    )


            display_animal_data(
                taxon,
                observations
    )
