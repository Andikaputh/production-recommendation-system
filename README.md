# Production-Grade Personalized Recommendation System

An end-to-end personalized recommendation system designed to demonstrate how a machine learning model can be developed, evaluated, integrated into an application, containerized, and deployed as a production-oriented AI service.

> **Portfolio Project — Machine Learning Engineering / AI Engineering / MLOps**

---

## Overview

Recommendation systems are an important component of modern digital platforms. They help users discover products, merchants, services, and other content that are more relevant to their interests and previous interactions.

This project explores the complete lifecycle of a recommendation system, starting from raw user-item interaction data and progressing through data preparation, model training, evaluation, candidate generation, database serving, API development, containerization, and cloud deployment.

Rather than focusing only on building a machine learning model, this project emphasizes the **engineering workflow required to turn a trained model into a usable recommendation service**.

The system is designed as a **production-minded simulation** inspired by recommendation use cases commonly encountered in large-scale e-commerce, food delivery, and marketplace platforms.

The overall workflow separates the machine learning process into two major components:

* **Offline pipeline:** data processing, model training, evaluation, and recommendation candidate generation.
* **Online serving:** retrieving precomputed recommendation candidates from a database and exposing them through a REST API.

This separation allows the computationally expensive machine learning process to be performed offline, while the online API can focus on fast retrieval and response generation.

> **Note:** This is an independent portfolio project and is **not affiliated with, based on, or using any internal system or data from GoTo or any other commercial platform.**

---

# Try It Live

The Recommendation API has been deployed publicly on Render.

You can simulate a recommendation request by replacing `123` with another user ID:

👉 https://production-recommendation-system.onrender.com/recommendations/123

For example:

```http
GET /recommendations/123
```

### Example API Response

```json
{
  "user_id": 123,
  "recommendation_type": "popularity_from_db",
  "recommendations": [
    {
      "item_id": 1,
      "score": 1.0
    },
    {
      "item_id": 4,
      "score": 0.985
    },
    {
      "item_id": 7,
      "score": 0.97
    },
    {
      "item_id": 8,
      "score": 0.965
    },
    {
      "item_id": 9,
      "score": 0.96
    }
  ]
}
```

The API response contains:

* `user_id` — the user requesting recommendations.
* `recommendation_type` — indicates which recommendation strategy was used.
* `recommendations` — the list of recommended items.
* `item_id` — the identifier of the recommended item.
* `score` — the recommendation score associated with the item.

The `popularity_from_db` response also demonstrates the system's fallback mechanism for cases where a personalized recommendation is not available.

---

# Project Objectives

The primary objectives of this project are:

1. Build a recommendation model from user-item interaction data.
2. Apply a time-based data splitting strategy to reduce the risk of temporal data leakage.
3. Implement a popularity-based baseline for comparison and cold-start handling.
4. Implement collaborative filtering using matrix factorization with TruncatedSVD.
5. Evaluate recommendation quality using both predictive and ranking-oriented metrics.
6. Track machine learning experiments using MLflow.
7. Extract recommendation candidates from the trained model.
8. Store recommendation candidates in a relational database.
9. Develop a REST API for recommendation retrieval.
10. Containerize the application using Docker.
11. Deploy the recommendation service to a cloud PaaS environment.

The project therefore covers not only the **modeling stage**, but also several components of the **machine learning engineering and MLOps lifecycle**.

---

# Tech Stack

The project uses a combination of data science, machine learning, backend engineering, database, and deployment technologies.

## Data & Machine Learning

### NumPy

Used for numerical operations required during data processing and model-related computations.

### Pandas

Used for:

* Loading interaction data.
* Data cleaning and transformation.
* Timestamp-based splitting.
* Feature preparation.
* Evaluation data preparation.

### Scikit-learn

Scikit-learn is used to implement the collaborative filtering component, particularly **TruncatedSVD** for matrix factorization.

The model is applied to a user-item interaction matrix to learn a lower-dimensional representation of users and items.

### Evaluation Metrics

The system evaluates the recommendation pipeline using:

* **RMSE**
* **Precision@10**
* **Recall@10**

Using multiple metrics provides a broader view of model performance.

RMSE focuses on the accuracy of predicted interaction values, while Precision@10 and Recall@10 evaluate the quality of the recommended Top-K items.

---

# API & Data Serving

## FastAPI

FastAPI is used to expose the recommendation system through a REST API.

The API provides an interface between the recommendation engine and potential client applications such as:

* Web applications
* Mobile applications
* Other backend services
* Testing clients

The API is intentionally separated from the training pipeline so that model training does not need to occur whenever a recommendation request is received.

## SQLite

SQLite is used as the relational database for storing recommendation candidates generated during the offline pipeline.

Instead of loading recommendation data from CSV files whenever an API request arrives, the online service retrieves the required records through database queries.

This provides a cleaner separation between:

**Recommendation generation → Database storage → API retrieval**

## SQLAlchemy

SQLAlchemy is used as the ORM layer between the FastAPI application and SQLite database.

This allows the application to interact with database records through Python models and queries rather than relying entirely on raw SQL statements.

---

# MLOps & Deployment

## MLflow

MLflow is used for local experiment tracking.

The training workflow can record relevant experiment information such as:

* Model parameters
* Evaluation metrics
* Experiment runs
* Model-related artifacts

This makes it easier to compare different experiments during model development.

## Docker

Docker is used to containerize the application and its runtime environment.

The goal is to make the application environment more reproducible by packaging the application together with its required dependencies.

The same containerized application can then be used as the deployment unit for the cloud environment.

## Render

Render is used as the cloud hosting platform for the deployed recommendation API.

The Dockerized application is deployed as a publicly accessible service, allowing the recommendation endpoint to be tested outside the local development environment.

---

# System Architecture

The system is divided into two primary stages:

1. **Offline Recommendation Pipeline**
2. **Online Recommendation Serving**

This separation is one of the key architectural concepts demonstrated by the project.

---

## Offline Pipeline

```text
==================== OFFLINE PIPELINE ====================

[Raw Interaction Data]
          |
          v
[Time-Based Data Split]
          |
          v
[User-Item Interaction Matrix]
          |
          v
[SVD Collaborative Filtering]
          |
          +--------------------+
          |                    |
          v                    v
 [Model Evaluation]      [Candidate Extraction]
          |                    |
          v                    v
      [MLflow]        [Recommendation Candidates]
                               |
                               v
                    [SQLite Database Seeding]

============================================================
```

The offline pipeline is responsible for the computationally heavier parts of the system.

### 1. Raw Data

The process begins with historical user-item interaction data.

The interaction data provides the basis for learning relationships between users and items.

### 2. Time-Based Split

Instead of randomly splitting the dataset, interactions are separated according to their timestamps.

Historical interactions are used for training, while later interactions are reserved for evaluation.

This approach is intended to better simulate the chronological nature of recommendation systems, where a model should use past behavior to make predictions about future behavior.

### 3. Interaction Matrix

The processed interactions are transformed into a user-item matrix.

Conceptually:

```text
             Item 1   Item 2   Item 3   Item 4
User 1          1        0        1        0
User 2          0        1        1        0
User 3          1        0        0        1
User 4          0        1        0        1
```

The matrix represents the relationship between users and items and becomes the input structure for the collaborative filtering model.

### 4. SVD Collaborative Filtering

TruncatedSVD is applied to reduce the dimensionality of the interaction matrix.

The model learns latent representations that can be used to estimate user-item affinity.

The resulting representation is then used to generate candidate recommendations for users.

### 5. Model Evaluation

The trained model is evaluated against the held-out portion of the dataset.

The evaluation includes:

* RMSE
* Precision@10
* Recall@10

These metrics provide different perspectives on the model's performance.

### 6. Candidate Extraction

Rather than performing the complete recommendation computation during every API request, recommendation candidates are generated during the offline stage.

The generated candidates are then prepared for serving.

### 7. Database Seeding

The generated recommendation candidates are inserted into the SQLite database.

This creates a serving layer between the machine learning pipeline and the API.

---

# Online Serving

```text
==================== ONLINE SERVING ====================

[Client / Application]
          |
          | HTTP GET
          v
[FastAPI Recommendation API]
          |
          | SQL Query
          v
[SQLAlchemy ORM]
          |
          v
[SQLite Database]
          |
          v
[Recommendation Response]

=========================================================
```

The online serving layer is intentionally lightweight.

When a client requests recommendations for a user, the API does not need to execute the entire model-training process.

Instead, it retrieves the appropriate recommendation candidates from the database and returns them as a JSON response.

For example:

```http
GET /recommendations/123
```

The request is handled by FastAPI, which queries the database through SQLAlchemy and returns the available recommendation candidates.

This architecture demonstrates a common principle in ML systems:

> **Perform expensive computation offline whenever possible, then keep online inference or retrieval lightweight enough for application use.**

---

# Recommendation Strategy

The project currently combines two recommendation approaches.

## 1. Collaborative Filtering

The primary machine learning approach uses collaborative filtering through matrix factorization.

The underlying assumption is that users with similar interaction patterns may have similar preferences.

By decomposing the user-item interaction matrix into lower-dimensional representations, the system attempts to capture latent relationships between users and items.

This enables the system to generate personalized candidate recommendations based on learned interaction patterns.

---

## 2. Popularity-Based Fallback

A recommendation system also needs to handle users for whom personalized information is insufficient.

This project therefore implements a popularity-based fallback strategy.

```text
User Request
     |
     v
Is personalized recommendation available?
     |
   /   \
 Yes    No
 |       |
 v       v
SVD    Popularity
 |       |
 +---+---+
     |
     v
Recommendation Response
```

The fallback uses popularity information stored in the database.

This is particularly useful for cold-start scenarios where the system does not have sufficient interaction information to produce a meaningful personalized recommendation.

---

# Evaluation & Methodology

Recommendation systems require careful evaluation because a model that performs well at predicting interaction values does not necessarily produce the best Top-K recommendations.

This project therefore uses both **predictive** and **ranking-oriented** metrics.

---

## Time-Based Data Splitting

The dataset is split according to time rather than using a purely random train-test split.

Conceptually:

```text
Past ------------------------------------------> Future

|---------------- Training ----------------|-- Test --|
```

The model learns from earlier interactions and is evaluated against later interactions.

This prevents future interactions from being unintentionally included in the training data and provides a more realistic evaluation setup for temporal recommendation scenarios.

---

## RMSE

**Root Mean Square Error (RMSE)** measures the difference between predicted and actual interaction values.

A lower RMSE indicates that the predicted values are, on average, closer to the observed values.

However, RMSE alone is not sufficient for evaluating a Top-K recommendation system because users typically care more about which items appear near the top of the recommendation list than about the exact predicted score.

---

## Precision@10

Precision@10 evaluates how many of the top 10 recommended items are relevant.

Conceptually:

```text
Top 10 Recommendations
        |
        v
Relevant Items / 10
        |
        v
Precision@10
```

A higher Precision@10 indicates that a larger proportion of the recommended items are relevant according to the evaluation criteria.

---

## Recall@10

Recall@10 measures how many of the relevant items available in the evaluation set were successfully included within the top 10 recommendations.

This complements Precision@10 by measuring the system's ability to retrieve relevant items.

---

# Cold-Start Handling

One of the practical challenges of recommendation systems is the **cold-start problem**.

A new user may have little or no historical interaction data. As a result, a collaborative filtering model may not have enough information to produce a personalized recommendation.

This project addresses that scenario through a popularity-based fallback.

```text
                 Recommendation Request
                          |
                          v
                 Check User History
                          |
             +------------+------------+
             |                         |
       Sufficient Data            Insufficient Data
             |                         |
             v                         v
    Personalized Model          Popularity Baseline
             |                         |
             +------------+------------+
                          |
                          v
                  Recommendation API
```

The fallback provides a recommendation response even when personalized recommendations cannot be generated.

---

# Production-Oriented Design

Although this project is not intended to represent a full production system at the scale of a major commercial platform, several design decisions are intentionally made with production concepts in mind.

### Separation of Offline and Online Workloads

Model training and recommendation candidate generation are separated from API serving.

This prevents expensive training operations from being performed as part of normal API requests.

### Database-Based Serving

Recommendation candidates are stored in a database rather than being loaded directly from CSV files for every request.

This creates a more application-oriented serving layer.

### Containerization

Docker provides a consistent runtime environment between development and deployment.

### Experiment Tracking

MLflow provides experiment tracking during model development, making it easier to compare different runs and configurations.

### Fallback Strategy

The popularity-based recommendation provides a basic mechanism for handling users who cannot receive personalized recommendations.

### Cloud Deployment

The final API is deployed publicly, making the system testable as an actual service rather than remaining exclusively inside a local development environment.

---

# Project Workflow

The complete workflow can be summarized as:

```text
Raw Data
   |
   v
Data Processing
   |
   v
Time-Based Split
   |
   v
Interaction Matrix
   |
   v
SVD Model
   |
   +--------------------+
   |                    |
   v                    v
Evaluation          Candidate Generation
   |                    |
   v                    v
 MLflow             SQLite Database
                        |
                        v
                  FastAPI Service
                        |
                        v
                      Docker
                        |
                        v
                      Render
                        |
                        v
                 Public API Endpoint
```

This workflow demonstrates the transition from **raw data → machine learning model → recommendation candidates → data serving → API → cloud deployment**.

---

# Current Status

🚧 **Project Milestones Achieved**

* [x] Project design & environment setup
* [x] Time-based data splitting pipeline
* [x] Popularity baseline generation
* [x] Matrix Factorization using SVD
* [x] RMSE evaluation
* [x] Precision@K evaluation
* [x] Recall@K evaluation
* [x] Experiment tracking using MLflow
* [x] Recommendation candidate extraction
* [x] Database data serving using SQLite
* [x] SQLAlchemy ORM integration
* [x] Recommendation API development using FastAPI
* [x] Application containerization using Docker
* [x] Cloud deployment using Render PaaS

---

# Future Improvements

The current implementation provides a foundation for a more advanced recommendation architecture. Several components could be improved in future iterations.

## Hybrid Recommendation System

The current collaborative filtering approach primarily relies on user-item interaction patterns.

A future version could combine collaborative filtering with content-based features to create a hybrid recommendation system.

For example:

```text
Collaborative Filtering
          +
Content-Based Features
          |
          v
     Hybrid Model
          |
          v
 Personalized Ranking
```

This could potentially improve recommendation quality, particularly for users or items with limited interaction history.

---

## Learning-to-Rank

A more advanced ranking layer could be introduced after candidate generation.

For example, a ranking model such as LightGBM could be used to learn how different candidate features contribute to the final ranking.

A potential future architecture would therefore become:

```text
User / Context
      |
      v
Candidate Generation
      |
      v
Candidate Pool
      |
      v
Ranking Model
      |
      v
Top-K Recommendations
```

---

## PostgreSQL

SQLite is currently sufficient for this portfolio implementation and provides a simple relational serving layer.

For a more realistic multi-instance deployment scenario, the database could be migrated to a managed PostgreSQL service.

This would provide a more suitable foundation for concurrent application workloads and cloud-based database management.

---

## Real-Time Feature Store

A future implementation could introduce a feature store for maintaining user and item features that change over time.

Examples could include:

* Recent user interactions
* Interaction frequency
* Item popularity
* Recency features
* User preference signals

This would allow the recommendation system to incorporate more dynamic information into the recommendation process.

---

## CI/CD

The deployment workflow could be further automated using GitHub Actions.

A potential pipeline would be:

```text
Git Push
   |
   v
Automated Tests
   |
   v
Docker Build
   |
   v
Deployment
   |
   v
Production API
```

Automated testing and deployment would make the project closer to a complete MLOps workflow.

---

# Limitations

This project is intentionally designed as a portfolio-scale implementation rather than a production system operating at internet-scale traffic.

The current architecture has several limitations:

* SQLite is a lightweight local database rather than a distributed production database.
* Recommendation candidates are generated offline rather than continuously updated in real time.
* The current model focuses on collaborative filtering rather than a hybrid ranking architecture.
* The feature set is limited compared with commercial recommendation systems.
* The deployment architecture does not currently include distributed model serving or autoscaling infrastructure.
* CI/CD automation is identified as a future improvement rather than part of the current implementation.

These limitations are intentional boundaries of the current project and provide clear directions for future development.

---

# Why This Project Matters

The main purpose of this project is not simply to demonstrate that a recommendation algorithm can be trained.

Instead, it demonstrates the broader workflow required to transform machine learning experimentation into an accessible software service.

The project connects several areas:

```text
Data Science
     |
     v
Machine Learning
     |
     v
Model Evaluation
     |
     v
MLOps
     |
     v
Backend Engineering
     |
     v
Database Serving
     |
     v
Containerization
     |
     v
Cloud Deployment
```

This makes the project representative of a **Machine Learning Engineering / AI Engineering workflow**, where building the model is only one part of the overall system.

---

# Author

**Andika**

Informatics Student | Machine Learning / AI Engineering Enthusiast

GitHub: https://github.com/Andikaputh

---

# License

This project is intended for educational and portfolio purposes.
