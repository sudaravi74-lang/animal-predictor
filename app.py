 import streamlit as st
from sklearn.tree import DecisionTreeClassifier

# Training data
# [weight, fur, flies, legs]

features = [
    [4, 1, 0, 4],       # Cat
    [20, 1, 0, 4],      # Dog
    [5, 0, 1, 2],       # Eagle
    [500, 0, 0, 4],     # Elephant
    [190, 1, 0, 4],     # Lion
    [220, 1, 0, 4],     # Tiger
    [400, 1, 0, 4],     # Horse
    [450, 1, 0, 4],     # Cow
    [8, 1, 0, 2],       # Monkey
    [2, 1, 0, 4]        # Rabbit
]

labels = [
    "Cat",
    "Dog",
    "Eagle",
    "Elephant",
    "Lion",
    "Tiger",
    "Horse",
    "Cow",
    "Monkey",
    "Rabbit"
]

# Create and train model
model = DecisionTreeClassifier()
model.fit(features, labels)

# App
st.title("🐾 Animal Predictor")

weight = st.number_input(
    "Animal weight (kg)",
    min_value=0.1,
    value=5.0
)

fur = st.selectbox(
    "Does it have fur?",
    ["Yes", "No"]
)

flies = st.selectbox(
    "Can it fly?",
    ["Yes", "No"]
)

legs = st.number_input(
    "Number of legs",
    min_value=0,
    max_value=8,
    value=4
)

if st.button("Predict"):

    fur_value = 1 if fur == "Yes" else 0
    flies_value = 1 if flies == "Yes" else 0

    prediction = model.predict(
        [[weight, fur_value, flies_value, legs]]
    )

    st.success("Prediction: " + prediction[0])
