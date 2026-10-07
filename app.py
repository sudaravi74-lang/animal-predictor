import streamlit as st
from sklearn.tree import DecisionTreeClassifier

# Training data
features = [
    [4, 1, 0],
    [20, 1, 0],
    [5, 0, 1]
]

labels = ["Cat", "Dog", "Eagle"]

# Create and train model
model = DecisionTreeClassifier()
model.fit(features, labels)

# App
st.title("🐾 Animal Predictor")

weight = st.number_input("Animal weight (kg)", min_value=0.1, value=5.0)

fur = st.selectbox("Does it have fur?", ["Yes", "No"])

flies = st.selectbox("Can it fly?", ["Yes", "No"])

if st.button("Predict"):
    fur_value = 1 if fur == "Yes" else 0
    flies_value = 1 if flies == "Yes" else 0

    prediction = model.predict([[weight, fur_value, flies_value]])

    st.success("Prediction: " + prediction[0])
