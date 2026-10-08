import streamlit as st
from sklearn.ensemble import RandomForestClassifier
from PIL import Image
import torch
from transformers import CLIPProcessor, CLIPModel


# =========================================================
# PAGE
# =========================================================

st.set_page_config(
    page_title="Animal Encyclopedia & Predictor",
    page_icon="🐾",
    layout="wide"
)

st.title("🐾 Animal Encyclopedia & Predictor")
st.write("Explore animals, identify animals using measurements, or identify an animal from an image.")


# =========================================================
# ANIMAL DATABASE
# =========================================================

animals = {

    "Dog": {
        "emoji": "🐶",
        "appearance": "Dogs have four legs, a tail, two ears and a muzzle.",
        "colour": "Many colours including black, white, brown, golden and mixed colours.",
        "body": "Medium-sized mammal with a muscular body.",
        "region": "Worldwide",
        "habitat": "Homes, farms, villages and cities.",
        "diet": "Omnivore",
        "size": "Small to large",
        "weight": "1–90 kg depending on breed",
        "lifespan": "10–13 years",
        "fact": "Dogs have an excellent sense of smell and are among humans' oldest domesticated companions."
    },

    "Cat": {
        "emoji": "🐱",
        "appearance": "Cats have a small flexible body, four legs, pointed ears, whiskers and a long tail.",
        "colour": "White, black, grey, orange, brown and many combinations.",
        "body": "Small, flexible and muscular body.",
        "region": "Worldwide",
        "habitat": "Homes, farms, cities and forests.",
        "diet": "Carnivore",
        "size": "Small",
        "weight": "2–8 kg",
        "lifespan": "12–18 years",
        "fact": "Cats can rotate their ears to detect sounds from different directions."
    },

    "Lion": {
        "emoji": "🦁",
        "appearance": "Large muscular cat. Adult males usually have a prominent mane.",
        "colour": "Yellowish, golden or brown.",
        "body": "Powerful body with strong legs and large paws.",
        "region": "Africa and a small population in India",
        "habitat": "Grasslands, savannas and open woodland.",
        "diet": "Carnivore",
        "size": "Large",
        "weight": "120–250 kg",
        "lifespan": "10–15 years in the wild",
        "fact": "Lions are the only big cats that commonly live in social groups called prides."
    },

    "Tiger": {
        "emoji": "🐯",
        "appearance": "Large cat with distinctive dark stripes.",
        "colour": "Orange, white and black.",
        "body": "Long muscular body with powerful legs.",
        "region": "Asia",
        "habitat": "Forests, grasslands and wetlands.",
        "diet": "Carnivore",
        "size": "Large",
        "weight": "75–300 kg",
        "lifespan": "10–15 years",
        "fact": "Every tiger has a unique stripe pattern."
    },

    "Elephant": {
        "emoji": "🐘",
        "appearance": "Huge body, long trunk, large ears and tusks in many individuals.",
        "colour": "Grey to dark grey.",
        "body": "Massive body supported by four thick legs.",
        "region": "Africa and Asia",
        "habitat": "Grasslands, forests and savannas.",
        "diet": "Herbivore",
        "size": "Very large",
        "weight": "2,000–6,000+ kg",
        "lifespan": "60–70 years",
        "fact": "Elephants use their trunks for breathing, smelling, drinking and grabbing objects."
    },

    "Horse": {
        "emoji": "🐴",
        "appearance": "Large four-legged animal with a long neck, mane, tail and hooves.",
        "colour": "White, black, brown, grey, chestnut and many combinations.",
        "body": "Strong athletic body with long legs.",
        "region": "Worldwide",
        "habitat": "Grasslands, farms and open areas.",
        "diet": "Herbivore",
        "size": "Large",
        "weight": "400–600 kg",
        "lifespan": "25–30 years",
        "fact": "Horses can sleep both standing up and lying down."
    },

    "Giraffe": {
        "emoji": "🦒",
        "appearance": "Very tall animal with an extremely long neck and long legs.",
        "colour": "Yellowish or orange with brown patches.",
        "body": "Tall body with long neck and legs.",
        "region": "Africa",
        "habitat": "Savannas, grasslands and open woodlands.",
        "diet": "Herbivore",
        "size": "Very large",
        "weight": "550–1,200 kg",
        "lifespan": "20–25 years",
        "fact": "Giraffes are the tallest living land animals."
    },

    "Panda": {
        "emoji": "🐼",
        "appearance": "Large bear-like animal with distinctive black-and-white fur.",
        "colour": "Black and white.",
        "body": "Round, heavy body with strong limbs.",
        "region": "China",
        "habitat": "Mountain forests.",
        "diet": "Mostly bamboo",
        "size": "Medium to large",
        "weight": "70–120 kg",
        "lifespan": "15–20 years in the wild",
        "fact": "Giant pandas spend many hours each day eating bamboo."
    },

    "Monkey": {
        "emoji": "🐒",
        "appearance": "Primates with hands, feet, expressive faces and usually a tail.",
        "colour": "Brown, grey, black, golden and other colours depending on species.",
        "body": "Agile body with flexible limbs.",
        "region": "Africa, Asia and the Americas depending on species.",
        "habitat": "Forests, grasslands and mountains.",
        "diet": "Omnivore",
        "size": "Small to medium",
        "weight": "Varies greatly by species",
        "lifespan": "Varies by species",
        "fact": "Many monkeys use complex social communication and live in groups."
    },

    "Zebra": {
        "emoji": "🦓",
        "appearance": "Horse-like animal famous for its black-and-white stripes.",
        "colour": "Black and white.",
        "body": "Strong body with four long legs and hooves.",
        "region": "Africa",
        "habitat": "Grasslands, savannas and open woodland.",
        "diet": "Herbivore",
        "size": "Medium to large",
        "weight": "175–450 kg",
        "lifespan": "20–25 years",
        "fact": "Every zebra has a unique stripe pattern."
    }
}


# =========================================================
# RANDOM FOREST MEASUREMENT MODEL
# =========================================================

features = [
    [40,70,10,4], [50,80,20,4], [60,100,30,4],
    [20,40,3,4], [25,45,4,4], [30,50,6,4],
    [100,180,150,4], [120,200,190,4], [130,220,220,4],
    [90,180,120,4], [100,200,180,4], [110,220,230,4],
    [250,400,3000,4], [300,500,5000,4], [350,600,6000,4],
    [140,220,400,4], [160,250,500,4], [170,270,600,4],
    [400,280,800,4], [500,300,1000,4], [550,350,1200,4],
    [60,120,70,4], [70,150,100,4], [80,170,120,4],
    [40,60,8,4], [60,80,15,4], [80,100,25,4],
    [120,200,250,4], [130,230,350,4], [150,250,400,4]
]

labels = [
    "Dog","Dog","Dog",
    "Cat","Cat","Cat",
    "Lion","Lion","Lion",
    "Tiger","Tiger","Tiger",
    "Elephant","Elephant","Elephant",
    "Horse","Horse","Horse",
    "Giraffe","Giraffe","Giraffe",
    "Panda","Panda","Panda",
    "Monkey","Monkey","Monkey",
    "Zebra","Zebra","Zebra"
]

model = RandomForestClassifier(
    n_estimators=100,
    random_state=42
)

model.fit(features, labels)


# =========================================================
# CLIP IMAGE MODEL
# =========================================================

@st.cache_resource
def load_clip_model():

    model = CLIPModel.from_pretrained(
        "openai/clip-vit-base-patch32"
    )

    processor = CLIPProcessor.from_pretrained(
        "openai/clip-vit-base-patch32"
    )

    return model, processor


# =========================================================
# DISPLAY ANIMAL INFORMATION
# =========================================================

def display_animal_info(animal_name):

    info = animals[animal_name]

    st.subheader(
        f"{info['emoji']} {animal_name}"
    )

    st.write(
        f"**Appearance:** {info['appearance']}"
    )

    st.write(
        f"**Colour:** {info['colour']}"
    )

    st.write(
        f"**Body:** {info['body']}"
    )

    st.write(
        f"**Region:** {info['region']}"
    )

    st.write(
        f"**Habitat:** {info['habitat']}"
    )

    st.write(
        f"**Diet:** {info['diet']}"
    )

    st.write(
        f"**Size:** {info['size']}"
    )

    st.write(
        f"**Weight:** {info['weight']}"
    )

    st.write(
        f"**Lifespan:** {info['lifespan']}"
    )

    st.info(
        f"💡 **Interesting Fact:** {info['fact']}"
    )


# =========================================================
# MAIN MENU
# =========================================================

option = st.radio(
    "Choose an option:",
    [
        "📚 Explore Animal",
        "🤖 Identify Unknown Animal",
        "📷 Identify Animal from Image"
    ]
)


# =========================================================
# 1. EXPLORE ANIMAL
# =========================================================

if option == "📚 Explore Animal":

    selected_animal = st.selectbox(
        "Select an animal:",
        list(animals.keys())
    )

    if st.button("Show Animal Information"):

        display_animal_info(selected_animal)


# =========================================================
# 2. IDENTIFY UNKNOWN ANIMAL
# =========================================================

elif option == "🤖 Identify Unknown Animal":

    st.subheader("Enter Animal Measurements")

    height = st.number_input(
        "Height (cm)",
        min_value=1.0,
        value=50.0
    )

    length = st.number_input(
        "Body Length (cm)",
        min_value=1.0,
        value=80.0
    )

    weight = st.number_input(
        "Weight (kg)",
        min_value=0.1,
        value=20.0
    )

    legs = st.number_input(
        "Number of Legs",
        min_value=0,
        max_value=10,
        value=4
    )

    if st.button("🔍 Identify Animal"):

        prediction = model.predict(
            [[height, length, weight, legs]]
        )[0]

        st.success(
            f"🐾 Predicted Animal: **{prediction}**"
        )

        display_animal_info(prediction)


# =========================================================
# 3. IDENTIFY ANIMAL FROM IMAGE
# =========================================================

elif option == "📷 Identify Animal from Image":

    st.subheader("📷 Upload an Animal Image")

    uploaded_image = st.file_uploader(
        "Choose an image:",
        type=["jpg", "jpeg", "png"]
    )

    if uploaded_image is not None:

        image = Image.open(uploaded_image).convert("RGB")

        st.image(
            image,
            caption="Uploaded Image",
            use_container_width=True
        )

        if st.button("🔍 Identify Animal"):

            with st.spinner("AI is analyzing the image..."):

                clip_model, processor = load_clip_model()

                animal_names = list(animals.keys())

                # Multiple descriptions make classification
                # more reliable than using only animal names.
                text_prompts = [
                    f"a clear photo of a {animal.lower()}"
                    for animal in animal_names
                ]

                inputs = processor(
                    text=text_prompts,
                    images=image,
                    return_tensors="pt",
                    padding=True
                )

                with torch.no_grad():

                    outputs = clip_model(**inputs)

                    logits_per_image = outputs.logits_per_image

                    probabilities = logits_per_image.softmax(
                        dim=1
                    )[0]

                best_index = torch.argmax(
                    probabilities
                ).item()

                predicted_animal = animal_names[
                    best_index
                ]

                confidence = (
                    probabilities[best_index].item()
                    * 100
                )

            st.success(
                f"🐾 Predicted Animal: **{predicted_animal}**"
            )

            st.write(
                f"AI confidence: **{confidence:.2f}%**"
            )

            display_animal_info(
                predicted_animal
            )

            # Show top 3 predictions
            st.subheader("🔎 Other Possible Results")

            top_values, top_indices = torch.topk(
                probabilities,
                k=3
            )

            for value, index in zip(
                top_values,
                top_indices
            ):

                animal = animal_names[
                    index.item()
                ]

                percentage = value.item() * 100

                st.write(
                    f"{animals[animal]['emoji']} "
                    f"**{animal}** — "
                    f"{percentage:.2f}%"
    )
