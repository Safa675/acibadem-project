# ACUHIT Hackathon: Project Ideas for a Quant

As a quantitative analyst transitioning into healthcare datathons, your strongest assets are your abilities to model complex time-series, assess and quantify risk, extract "alpha" (predictive signals) from messy data, and build robust predictive models. The ACUHIT Dynamic Health Scoring Challenge strongly aligns with these skills, particularly because it emphasizes **dynamic scoring** and **clinical outcome prediction**. 

Here are five project ideas specifically tailored for your quant background that perfectly align with the competition rules.

---

## 1. The "Health VaR" (Value at Risk) Model: Dynamic Patient Trajectory
**Concept:** In quantitative finance, Value at Risk (VaR) measures the risk of loss for investments. You can adapt this to healthcare by modeling a patient's health trajectory as a stochastic process (like an asset price). 
**Goal:** Create a "Health Score" index based on lab results and vitals. Then, use volatility metrics to predict the probability that a patient's health score will drop below a critical threshold (e.g., intensive care requirement) within the next $N$ days.
* **Relevant Rule:** Addresses *Dynamic Health Scoring* and *Predict Clinical Outcomes (Prognosis)*.
* **Data Used:** Time-series of `labdata.ods`, `recete.ods` (medication interventions), and vital signs.
* **Quant Appeal:** Uses stochastic calculus, volatility modeling (GARCH models on health vitals), and time-series forecasting. It's a highly original, mathematically rigorous approach that judges will love.

## 2. Clinical "Alpha" Generation via Turkish NLP
**Concept:** Quants often use NLP on corporate 10-K filings and earnings calls to predict stock movements. Apply this exact pipeline to Turkish clinical notes to predict patient prognosis and Length of Stay (LOS).
**Goal:** Build a robust NLP pipeline using pre-trained Turkish models (like Turkish BERT/BERTurk) to parse doctor/nurse notes from `anadata.ods`. Extract hidden risk factors and "clinical sentiment" (e.g., deteriorating vs. improving). Combine this unstructured text "alpha" with structured lab data to create a superior ensemble prediction model.
* **Relevant Rule:** Directly addresses *Process Unstructured Clinical Data* using NLP.
* **Data Used:** Unstructured text from `anadata.ods` (doctor's notes, epikriz reports).
* **Quant Appeal:** Information extraction, transformer models, feature engineering, and creating proprietary predictive factors from raw text.

## 3. The "S&P 500" Index of Systemic Health (Latent Factor Model)
**Concept:** Rather than looking at individual lab results, construct a composite index of a patient's overall health using quantitative factor models.
**Goal:** Apply Principal Component Analysis (PCA) or Autoencoders to the high-dimensional `labdata.ods` and `recete.ods`. Identify the 3-5 latent "macro factors" driving a patient's health. Create a mathematically sound, standardized health index (e.g., scaled 0 to 100) that updates dynamically with every new lab or prescription.
* **Relevant Rule:** Directly addresses *Develop Dynamic Health Scoring* (creating novel health metrics not currently in literature).
* **Data Used:** `labdata.ods`, `recete.ods`, `anadata.ods`.
* **Quant Appeal:** Dimensionality reduction, index construction, cross-sectional ranking. You are essentially building a market capitalization-weighted index, but for physiological systems.

## 4. Hospital Capacity Yield Curve & Survival Analysis
**Concept:** Model patient Length of Stay (LOS) similarly to how quants model bond duration, yield curves, or mortgage prepayment speeds. 
**Goal:** Treat the hospital's capacity as a portfolio of fixed-income instruments. Use Survival Analysis (Cox Proportional Hazards models or Kaplan-Meier estimators) on `anadata.ods` to predict the exact probability distribution of a patient's discharge day. Aggregate this across all patients to forecast hospital resource utilization and bottleneck risks.
* **Relevant Rule:** Addresses *Predict Clinical Outcomes (Length of Stay and Resource Utilization needs)*.
* **Data Used:** `anadata.ods` (admission and discharge data, patient profiles).
* **Quant Appeal:** Survival models, duration matching, portfolio-level risk aggregation. This demonstrates how a predictive model can be operationalized for hospital management.

## 5. Health Credit Rating System (Probability of Default)
**Concept:** Treat adverse clinical outcomes (like severe complications or readmission) as a "default event".
**Goal:** Build a scoring system that assigns every patient a "rating" (e.g., AAA, BBB, CCC) representing their clinical stability. Train an XGBoost or LightGBM model on historical data (`labdata.ods`, `recete.ods`, and NLP features) to output a calibrated Probability of Default (PD). 
* **Relevant Rule:** Addresses *Dynamic Health Scoring* and *Predict Clinical Outcomes*.
* **Data Used:** All available datasets (`anadata.ods`, `labdata.ods`, `recete.ods`).
* **Quant Appeal:** Logistic regression, gradient boosting, rigorous cross-validation, hyperparameter tuning, and probability calibration. You can also showcase model interpretability (e.g., SHAP values) to explain *why* a patient is "downgraded," matching the transparency required in both finance and healthcare.

---

### Advice for the Stage 1 Video Submission:
Since the evaluation heavily weights **Originality (25%)** and **Technical Competence**, leaning into your quant background is a massive advantage. You aren't just another data scientist running a random forest; you are applying *financial risk mechanics* to patient survival trajectories. Make sure to frame your solution this way in your 5-minute technical presentation!
