# KasirGo Backend API 🚀

> A robust, secure, and scalable high-performance backend API powering the **[KasirGo POS Mobile Application](https://github.com/SiEncan/KasirGo)**. Built with Django REST Framework and optimized for deployment on Vercel.

**📱 Client Application / Frontend**  
This backend is the engine for the **KasirGo Mobile App**. For the full product showcase, UI demos, KDS workflows, and architectural deep-dives, please visit the **[Frontend Repository](https://github.com/SiEncan/KasirGo)**.

## 📖 Overview
The KasirGo Backend serves as the central nervous system for retail operations. It manages authentication, inventory synchronization, and transaction logging with ACID compliance. It is designed to be **stateless** and efficiently handles concurrent requests from multiple POS terminals.

## ✨ Key Features & Architecture

### 🏢 SaaS Multi-Tenancy
-   **Cafe Isolation**: All data (`User`, `Product`, `Transaction`) is strictly scoped to a specific `Cafe` entity.
-   **Secure Filtering**: API ViewSets automatically filter QuerySets based on `request.user.cafe`, preventing cross-tenant data leaks.

### 🔐 Hybrid Authentication (Django + Firebase)
-   **JWT Core**: Uses `simplejwt` for secure, stateless REST API access.
-   **Firebase Bridge**: Custom endpoint `/auth/firebase-token/` generates **Firebase Custom Tokens** with `cafe_id` claims, enabling secure, scoped access to Realtime Database.

### 👨‍🍳 Kitchen Display Support (KDS)
-   **Smart Logic**: Products have `needs_preparation` flags to determine if they should appear on KDS.
-   **Workflow Tracking**: Supports granular statuses (`pending` -> `cooking` -> `served`) for kitchen efficiency.

### 📦 Inventory Management
-   **Cloudinary Integration**: Automatic optimizations for product image storage.
-   **Atomic Stock Control**: Prevents race conditions during simultaneous checkouts.

### 📊 Advanced Reporting
-   **Transaction Searching**: optimized `Q` object filtering for finding transactions by ID, Customer Name, or Notes.

## 🧰 Tech Stack

![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54) ![Django](https://img.shields.io/badge/django-%23092E20.svg?style=for-the-badge&logo=django&logoColor=white) ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-336791?style=for-the-badge&logo=postgresql&logoColor=white) ![Neon](https://img.shields.io/badge/Neon-00E599?style=for-the-badge&logo=neon&logoColor=black) ![Vercel](https://img.shields.io/badge/vercel-%23000000.svg?style=for-the-badge&logo=vercel&logoColor=white) ![Firebase](https://img.shields.io/badge/Firebase-FFCA28?style=for-the-badge&logo=firebase&logoColor=black)
  
-   **Framework**: [Django 5.2](https://www.djangoproject.com/) & [Django REST Framework](https://www.django-rest-framework.org/)
-   **Database**: PostgreSQL (Production) / SQLite (Dev)
-   **Storage**: Cloudinary (CDNs for static/media files)
-   **Authentication**: `simplejwt` (JWT) & `firebase-admin` (Custom Tokens)
-   **Deployment**: Vercel (Serverless Config) with `whitenoise` for static files.

## 🚀 Deployment (Vercel)

 This project is optimized for **Serverless Deployment**.
 
 1.  **`vercel.json`**: Configured for WSGI application interface.
 2.  **`build_files.sh`**: Custom script to handle migrations and static collection during the build phase.
 3.  **Database**: Connects to external PostgreSQL Neon Database via `dj_database_url`.

## 🏁 Installation

### Prerequisites
-   Python 3.10+
-   PostgreSQL (Optional for local dev)

### Steps

1.  Clone the repo
    ```bash
    git clone https://github.com/SiEncan/KasirGo-Backend.git
    ```
2.  Create Virtual Environment
    ```bash
    python -m venv venv
    source venv/bin/activate  # Windows: venv\Scripts\activate
    ```
3.  Install Dependencies
    ```bash
    pip install -r requirements.txt
    ```
4.  Run Migrations & Server
    ```bash
    python manage.py migrate
    python manage.py runserver
    ```

---
