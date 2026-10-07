import streamlit as st
from sklearn.tree import DecisionTreeClassifier

features = [
    [4, 1, 0, 4],
    [20, 1, 0, 4],
    [5, 0, 1, 2],
    [500, 0, 0, 4],
    [190, 1, 0, 4],
    [220, 1, 0, 4],
    [400, 1, 0, 4],
    [450, 1, 0, 4],
    [8, 1, 0, 2],
    [2, 1, 0, 4]
]

labels = [
    "Cat", "Dog", "Eagle", "Elephant", "Lion",
    "Tiger", "Horse", "Cow", "Monkey", "Rabbit"
]

model = DecisionTreeClassifier()
model.fit(features, labels)

st.title("🐾 Animal Predictor")

weight = st.number_input("Animal weight (kg)", min_value=0.1, value=5.0)

fur = st.selectbox("Does it have fur?", ["Yes", "No"])

flies = st.selectbox("Can it fly?", ["Yes", "No"])

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
