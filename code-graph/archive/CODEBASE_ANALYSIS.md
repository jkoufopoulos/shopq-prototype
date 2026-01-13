# CODEBASE_ANALYSIS.md

# 📊 MailQ Codebase Analysis

**Generated:** October 22, 2025 at 03:07

---

## 📈 Statistics at a Glance

| Metric | Value |
|--------|-------|
| Total Files | 41 |
| Python Files | 30 |
| JavaScript Files | 11 |
| Total Lines of Code | 5,654 |
| Total Classes | 16 |
| Total Functions | 57 |

---

## 🐍 Python Backend Analysis

### 📄 `experiments/src/__init__.py`

**AI Summary:** SUMMARY: This empty `__init__.py` file declares the `experiments/src` directory as a Python package, enabling its internal modules to be imported and organized within the project.

RELATIONSHIPS: This file marks `experiments.src` as a Python package, enabling other parts of the codebase to import modules from it (e.g., `from experiments.src import trainer`). Any code consuming `experiments.src` modules implicitly depends on this `__init__.py` for correct package resolution. Its role is purely structural, facilitating module organization and discoverability across the entire project.

---

### 📄 `experiments/src/ai_utils.py`

**AI Summary:** SUMMARY: This legacy `ai_utils.py` file serves as a backward-compatible wrapper for email classification, delegating calls to the newer `mailq.LLMClassifier`, and includes a text cleaning utility, with a clear intention for deprecation.

RELATIONSHIPS: This file is a deprecated compatibility layer within the `experiments` module. It dynamically adds `mailq` to the Python path to import and utilize the `LLMClassifier` and `CategoryManager` from the `mailq` package, acting as a wrapper for email classification and providing a text cleaning utility. Older components within the codebase currently depend on its `classify_email` function, but are explicitly encouraged to migrate directly to `mailq.LLMClassifier` as this file is slated for removal.

**Purpose:** Legacy wrapper for backward compatibility.

**Functions:**
- `_get_classifier()`
- `clean_text()`
- `classify_email()`

---

### 📄 `experiments/src/compare_gemini_gpt.py`

**AI Summary:** SUMMARY: This file compares email classification performance between a local `MemoryClassifier` and GPT-4o, using a shared category system, focusing on pure classification without reasoning.

RELATIONSHIPS: This file is an experimental script that depends on `MemoryClassifier` and `CategoryManager` from the `mailq` directory, utilizing their definitions for categories and one of the classifiers. It integrates the OpenAI API to provide a GPT-4o classification, benchmarking its output against the local `MemoryClassifier`. Its role is evaluative; it's not a core operational component but an assessment tool to compare different classification models.

**Purpose:** Compare Gemini vs GPT-4 classification on 100 emails

**Functions:**
- `classify_with_gpt()`
- `check_rule_match()`

---

### 📄 `experiments/src/fetch_emails.py`

**AI Summary:** SUMMARY: This file authenticates with the Google Gmail API using OAuth2 to fetch a specified number of recent emails, extracting their subject, sender, and a snippet for processing.

RELATIONSHIPS: This file serves as an API client, providing a utility function to fetch email data from Gmail via OAuth2. It depends on `token.json` and `credentials.json` located at the project's root (`../../credentials/`) for authentication. Other modules, likely within the `experiments` directory, would import and call its `fetch_unread_emails` function to retrieve email data for further processing.

**Functions:**
- `get_service()`
- `fetch_unread_emails()`

---

### 📄 `experiments/src/label_setup.py`

**AI Summary:** SUMMARY: This script authenticates with Gmail, fetches user labels, and interactively configures AI-driven email categorization settings for selected labels, saving the schema to a JSON file.

RELATIONSHIPS: This file serves as an interactive setup wizard, depending on a pre-existing `credentials.json` file for Google OAuth and generating `token.json` for persistent credentials. Its main output, `label_schema.json`, is then consumed by other AI components responsible for email classification, which utilize the defined label descriptions and importance to process and organize messages. It acts as an initial configuration entry point for the system.

**Functions:**
- `get_gmail_service()`
- `fetch_labels()`
- `run_label_setup_wizard()`

---

### 📄 `experiments/src/label_utils.py`

**AI Summary:** SUMMARY: This file provides utility functions for managing Gmail labels, including fetching existing labels, creating new ones, and applying them to specific emails.

RELATIONSHIPS: This file serves as a utility module for Gmail label management, depending on `fetch_emails.py` for acquiring an authenticated Gmail API service object. Its functions are likely imported and utilized by other parts of the codebase, such as email processing or categorization scripts, to programmatically interact with Gmail labels.

**Functions:**
- `get_gmail_labels()`
- `apply_label_to_email()`
- `create_gmail_label()`

---

### 📄 `experiments/src/remove_priority.py`

**AI Summary:** SUMMARY: This utility script modifies `experiment_runner.py` by removing all code related to "priority" assignment, calculation, and display, effectively stripping out a specific feature from that file.

RELATIONSHIPS: This file is a standalone utility script that directly modifies `experiment_runner.py` by reading its content, applying string and regex replacements, and then overwriting the file. It depends only on Python's built-in `re` module and is not imported by any other component; instead, its role is to act as a code transformation tool, likely used during development or experimentation to reconfigure `experiment_runner.py` by disabling the priority feature.

**Functions:**
- `remove_priority_from_file()`

---

### 📄 `mailq/__init__.py`

**AI Summary:** SUMMARY: This file initializes the MailQ package, exposing its core `RulesEngine` and `MemoryClassifier` components as part of its public API, and declares the package version.

RELATIONSHIPS: This file acts as the primary public interface and package initializer for the `mailq` system. It directly depends on `mailq/rules_engine.py` and `mailq/memory_classifier.py`, importing their classes to make them accessible directly from the `mailq` package namespace. Other parts of the codebase that utilize MailQ's core logic will typically import these components via `from mailq import RulesEngine`, establishing this `__init__.py` as a central access point to the system's core functionalities.

**Purpose:** MailQ Production System

**Dependencies (internal):**
- `mailq/memory_classifier.py`
- `mailq/rules_engine.py`

---

### 📄 `mailq/api.py`

**AI Summary:** SUMMARY: This file initializes the MailQ FastAPI server, orchestrating core services like email classification and feedback management, defining API models, and integrating specialized endpoint routers.

RELATIONSHIPS: This file serves as the primary entry point and API layer for the MailQ application, setting up the FastAPI server and configuring global middleware. It instantiates and depends on `MemoryClassifier`, `CategoryManager`, and `FeedbackManager` for core email processing, passing these services as dependencies to integrated API routers from `mailq.api_debug` and `mailq.api_feedback`. This centralizes the instantiation and connection of various internal components to expose a comprehensive set of endpoints.

**Purpose:** FastAPI server for MailQ email classification

**Classes:**
- `EmailInput`
- `EmailBatch`
- `ClassificationResult`
- `OrganizeResponse`
- `CategoryCreate`
- `RuleCreate`
- `RuleUpdate`
- `Config`
- `Config`

**Functions:**
- `root()`
- `health()`

**Dependencies (internal):**
- `mailq/api_debug.py`
- `mailq/api_feedback.py`
- `mailq/api_organize.py`
- `mailq/category_manager.py`
- `mailq/feedback_manager.py`
- *(+2 more)*

---

### 📄 `mailq/api_dashboard.py`

**AI Summary:** SUMMARY: This file provides utility functions to dynamically render a comprehensive HTML dashboard for visualizing MailQ's feedback, including statistics, correction patterns, and recent activities, based on provided data.

RELATIONSHIPS: This file acts as an HTML templating utility or presentation layer within the MailQ system. It is imported and utilized by `mailq/api_feedback.py`, which is likely an API endpoint responsible for gathering the necessary data and then calling `render_dashboard` to generate the HTML response for a web request. While it depends on standard Python libraries like `datetime` for formatting, it primarily relies on receiving structured data from other MailQ components (via `api_feedback.py`) to construct the visual dashboard.

**Purpose:** Dashboard HTML rendering for feedback visualization

**Functions:**
- `render_dashboard()`
- `_get_dashboard_css()`
- `_render_top_senders()`
- `_render_patterns()`
- `_render_recent_corrections()`

---

### 📄 `mailq/api_debug.py`

**AI Summary:** SUMMARY: This file defines FastAPI debug endpoints to expose and summarize the results and statistics of the most recent email classification batch, aiding in runtime monitoring.

RELATIONSHIPS: This file serves as an API layer for debugging, imported and mounted by `mailq/api.py` into the main FastAPI application. It depends on the core classification processing logic (likely orchestrated by `api.py`) to actively update its global `last_batch_store` via the `set_last_batch` function. This enables developers to remotely monitor the outcome and performance of classification batches, providing immediate insights into system operations.

**Purpose:** Debug endpoints for monitoring classification batches

**Functions:**
- `set_last_batch()`

---

### 📄 `mailq/api_feedback.py`

**AI Summary:** SUMMARY: This file defines FastAPI endpoints for submitting user corrections on email classifications, retrieving learning statistics, and serving a feedback dashboard.

RELATIONSHIPS: This file acts as an API layer, providing external access to the feedback system. It critically depends on `mailq.feedback_manager` for handling the core business logic of recording and querying feedback, and utilizes `mailq.api_dashboard` to render its HTML dashboard. The `mailq/api.py` module imports this file's `APIRouter` to integrate these endpoints into the main application, making it the primary interface for user interaction with the feedback mechanism.

**Purpose:** Feedback API endpoints for user corrections

**Classes:**
- `FeedbackInput`
- `Config`

**Functions:**
- `set_feedback_manager()`

**Dependencies (internal):**
- `mailq/api_dashboard.py`
- `mailq/feedback_manager.py`

---

### 📄 `mailq/api_organize.py`

**AI Summary:** SUMMARY: This file provides core logic for classifying a batch of emails, applying confidence thresholds, filtering labels, and collecting statistics, primarily for the `/api/organize` API endpoint.

RELATIONSHIPS: This file acts as a core logic component, specifically handling email classification for the `/api/organize` endpoint. It critically depends on an external `classifier` object (likely an AI model or rule engine) passed during runtime to perform the actual classification. The `mailq/api.py` module imports and utilizes the `classify_batch` function from this file, making it an essential backend processing layer for the Mailq API.

**Purpose:** Email classification logic for /api/organize endpoint

**Functions:**
- `classify_batch()`
- `_update_stats()`
- `_filter_labels()`
- `_print_low_confidence()`
- `_print_classification()`
- `_create_error_result()`
- `_print_summary()`

---

### 📄 `mailq/category_manager.py`

**AI Summary:** SUMMARY: This file manages user-specific email categories, storing them in an SQLite database and providing methods to retrieve, initialize with defaults, and add custom categories.

RELATIONSHIPS: This file acts as a core data access and business logic component for email category management, used by `mailq/api.py` to expose category-related functionalities. It depends on `config/default_categories.py` to retrieve predefined category lists for initial user setup or when a user has no custom categories.

**Purpose:** Manage user-specific email categories

**Classes:**
- `CategoryManager` (7 methods)

---

### 📄 `mailq/config/__init__.py`

**AI Summary:** SUMMARY: This file centralizes MailQ's core configuration, defining project paths, database location, enumerated email classification attributes (types, domains), and a comprehensive list of valid Gmail labels.

RELATIONSHIPS: This configuration file serves as a central source of truth for MailQ's system-wide constants, making it a foundational dependency for numerous other components. Modules like database connectors, data classification logic, or any part interacting with Gmail labels will import these definitions, ensuring consistent paths, data categories, and valid label structures across the codebase. While it indirectly references `Schema.json` and `mapping.py` for its definitions, this file itself is a core utility that *provides* these structured constants to the rest of the MailQ system.

**Purpose:** Configuration module for MailQ.

---

### 📄 `mailq/config/database.py`

**AI Summary:** SUMMARY: This file provides a centralized SQLite database configuration, managing connections, transactions, and schema validation to serve as the core data access layer for the 'mailq' application.

RELATIONSHIPS: This file serves as the foundational data access layer for the `mailq` application, providing the necessary utilities to connect to, manage, and interact with the SQLite database. Components such as `mailq/rules_manager.py` explicitly depend on it to perform all database operations, ensuring consistent connection settings, transaction handling, and schema integrity without needing to directly interact with the `sqlite3` module. It itself relies only on Python's standard library for its functionality.

**Purpose:** Centralized database configuration

**Functions:**
- `get_db_path()`
- `get_db_connection()`
- `db_transaction()`
- `execute_query()`
- `validate_schema()`
- `get_test_db_connection()`
- `init_database()`

---

### 📄 `mailq/config/default_categories.py`

**AI Summary:** SUMMARY: This file defines a constant list of default email categories, each with a name, description, and color, intended for new user accounts within the MailQ system.

RELATIONSHIPS: This file acts as a self-contained configuration data source, defining a `DEFAULT_CATEGORIES` list without any external dependencies. Other `mailq` system components, such as user creation or email processing modules, would import and utilize this list to initialize default email categories for new users. Its role is to provide a standardized, pre-defined set of initial categorization options for the application.

**Purpose:** Default email categories for new users

---

### 📄 `mailq/config/settings.py`

**AI Summary:** SUMMARY: This file centralizes application-wide settings, environment variables, API configurations, and feature flags by reading values from environment variables or providing sensible defaults for the MailQ application.

RELATIONSHIPS: This file primarily depends on the `os` module to read environment variables and `pathlib.Path` for defining project directory structures. Virtually every other component within the `mailq` application, including API endpoints, AI classification logic, feature flag checks, and logging setup, imports and utilizes these settings to configure their behavior and integrate with external services like Google Cloud or OpenAI. It acts as the core configuration provider, centralizing all configurable parameters to ensure consistent application-wide behavior across different environments.

**Purpose:** Application-wide settings and environment configuration

**Functions:**
- `is_production()`
- `is_development()`
- `get_env()`

---

### 📄 `mailq/feedback_manager.py`

**AI Summary:** SUMMARY: The `FeedbackManager` class stores user corrections, learns classification patterns, and manages few-shot examples in a SQLite database to continuously improve the `mailq` system's email classification accuracy.

RELATIONSHIPS: This file acts as a core data persistence layer, managing a SQLite database for feedback and learning. It depends on standard Python libraries like `sqlite3` for database interaction. Other components, specifically `mailq/api.py` and `mailq/api_feedback.py`, utilize this manager to store user corrections and retrieve learned patterns, while `mailq/vertex_gemini_classifier.py` likely fetches patterns and few-shot examples to enhance its AI-driven classification process.

**Purpose:** Feedback management for user corrections.

**Classes:**
- `FeedbackManager` (11 methods)

---

### 📄 `mailq/logger.py`

**AI Summary:** SUMMARY: This file provides a utility function to centrally configure and return a standardized Python logger that outputs formatted messages to standard output, preventing duplicate handlers.

RELATIONSHIPS: This file serves as a utility for centralized, consistent logging within the `mailq` application. It depends on Python's built-in `logging` and `sys` modules to configure loggers that output formatted messages to `sys.stdout`. Other components, such as `mailq/rules_engine.py`, import and use its `setup_logger` function to acquire these pre-configured loggers, ensuring uniform log output across the system.

**Purpose:** Centralized logging - CREATE THIS FILE

**Functions:**
- `setup_logger()`

---

### 📄 `mailq/mapper.py`

**AI Summary:** SUMMARY: This file is a utility that converts semantic email classification results, encompassing dimensions like type, domain, and attention, into a structured list of Gmail label strings based on defined confidence thresholds.

RELATIONSHIPS: This file acts as a core mapping utility, primarily imported and used by `mailq/memory_classifier.py`. It takes the raw classification output from `memory_classifier.py` and transforms it into an actionable format suitable for applying Gmail labels. Its role is to bridge the internal semantic classification logic with the external mechanism of organizing emails through labels.

**Purpose:** Gmail label mapper - converts semantic classification to Gmail label strings

**Functions:**
- `map_to_gmail_labels()`
- `validate_classification_result()`

---

### 📄 `mailq/memory_classifier.py`

**AI Summary:** SUMMARY: This file provides a memory-enhanced email classifier that prioritizes rule-based classification, falling back to a Vertex AI Gemini LLM, and mapping results to Gmail labels.

RELATIONSHIPS: This file acts as the core classification logic, orchestrating rule-based matching using `mailq.rules_engine` and leveraging `mailq.vertex_gemini_classifier` for LLM inference when rules don't match. It further depends on `mailq.mapper` for result transformation and validation, and is a foundational component directly consumed by `mailq/api.py` to expose the primary email classification functionality.

**Purpose:** Memory-enhanced email classifier using rules + LLM with Vertex AI

**Classes:**
- `MemoryClassifier` (5 methods)

**Dependencies (internal):**
- `mailq/mapper.py`
- `mailq/rules_engine.py`
- `mailq/vertex_gemini_classifier.py`

---

### 📄 `mailq/rules_engine.py`

**AI Summary:** SUMMARY: This file implements a rules engine for email classification, storing user-defined and learned patterns in an SQLite database to categorize incoming messages based on various criteria.

RELATIONSHIPS: This file relies on `mailq/logger.py` for standardized logging across the application. As a core logic component, it is imported by `mailq/__init__.py`, making its `RulesEngine` class a publicly accessible part of the `mailq` package. Additionally, `mailq/memory_classifier.py` imports this file, likely integrating its persistent, database-backed email classification rules into a broader classification strategy.

**Purpose:** Rules-based email classification with learning

**Classes:**
- `RulesEngine` (13 methods)

**Dependencies (internal):**
- `mailq/logger.py`

---

### 📄 `mailq/rules_manager.py`

**AI Summary:** SUMMARY: This module manages email classification rules by providing functions for CRUD operations like fetching, adding, updating, and deleting rules stored in the database.

RELATIONSHIPS: This file heavily depends on `mailq/config/database.py` to handle all its database connections and transactions for persistent storage of classification rules. It is imported and utilized by `mailq/api.py`, suggesting that the API layer exposes these rule management functionalities, making this file a core backend logic component for the system's rule-based email classification.

**Purpose:** Rules Management Module

**Functions:**
- `get_rules()`
- `add_rule()`
- `update_rule()`
- `delete_rule()`
- `get_rule_stats()`

**Dependencies (internal):**
- `mailq/config/database.py`

---

### 📄 `mailq/scripts/consolidate_databases.py`

**AI Summary:** SUMMARY: This script consolidates various Mailq system databases, including rules and learned patterns, into a single `mailq.db` file, creating a unified and initialized data store.

RELATIONSHIPS: This utility script is crucial for initializing and consolidating the Mailq application's central data store, `mailq.db`, defining its foundational schema for rules, categories, feedback, and learned patterns. It depends on an existing `rules.sqlite` file for initial data population and `sqlite3` for database operations. Crucially, all other Mailq components that manage or utilize email classification, rules, categories, or feedback will depend on the `mailq.db` created and maintained by this script as their primary data source.

**Purpose:** Consolidate all databases into mailq/data/mailq.db

**Functions:**
- `consolidate()`

---

### 📄 `mailq/scripts/inspect_databases.py`

**AI Summary:** SUMMARY: This Python script connects to project SQLite databases, extracts table schema, row counts, and sample data, then prints a comprehensive diagnostic report to the console.

RELATIONSHIPS: This utility script critically depends on the Python `sqlite3` module for database interaction and implicitly relies on the existence and structure of SQLite database files (e.g., `mailq.db`, `rules.db`) that are created and managed by other parts of the `mailq` application. It functions as a standalone developer tool, designed for direct command-line execution to debug or monitor the application's data stores, rather than being integrated into the core `mailq` runtime logic or being depended upon by other internal components.

**Purpose:** Inspect all databases and show their contents

**Functions:**
- `inspect_db()`
- `main()`

---

### 📄 `mailq/vertex_gemini_classifier.py`

**AI Summary:** SUMMARY: This file initializes a Vertex AI Gemini 2.0 Flash model to classify emails multi-dimensionally (type, domain, attention) using both static and dynamically learned few-shot examples from user feedback.

RELATIONSHIPS: This file depends on `mailq.feedback_manager.py` to retrieve learned classification patterns, dynamically enhancing its few-shot examples based on user corrections. Conversely, `mailq.memory_classifier.py` imports and likely utilizes this `VertexGeminiClassifier` as a core component for performing intelligent, multi-dimensional email classification within the broader MailQ system, acting as its AI-powered classification engine.

**Purpose:** Vertex AI Gemini - Multi-dimensional email classifier

**Classes:**
- `VertexGeminiClassifier` (8 methods)

**Dependencies (internal):**
- `mailq/feedback_manager.py`

---

### 📄 `scripts/bootstrap_from_gold_standard.py`

**AI Summary:** SUMMARY: This script populates the `rules.db` database by reading manually labeled email classifications from a CSV file and adding them as rules via the `RulesEngine` component.

RELATIONSHIPS: This utility script heavily depends on the `RulesEngine` class (imported from `mailq/rules_engine.py`) to store and manage the learned rules within `data/rules.db`. It consumes a "gold standard" CSV dataset (`data/100_emails/email_eval_dataset.csv`), effectively bootstrapping the foundational rule set that other core components, such as an API, will then utilize for live email classification.

**Purpose:** Bootstrap rules database from manually labeled emails

**Functions:**
- `bootstrap_rules()`

---

### 📄 `scripts/fetch_emails.py`

**AI Summary:** SUMMARY: This script authenticates with the Google Gmail API, fetches a specified count of recent emails, and extracts their subject, sender, and a snippet for further processing.

RELATIONSHIPS: This file serves as an API integration layer, depending on Google's client libraries and specific `credentials/token.json` and `credentials/credentials.json` files for authentication with Gmail. Other components within the codebase would import and utilize its `fetch_unread_emails` function to retrieve raw email data, abstracting the complexities of Google API calls and user authentication. Its role is a core utility responsible for fetching email messages, acting as the primary data source from Gmail for the rest of the application.

**Functions:**
- `get_service()`
- `fetch_unread_emails()`

---

### 📄 `scripts/fetch_emails_bulk.py`

**AI Summary:** SUMMARY: This script safely fetches a large volume of unread Gmail emails in batches, creating a CSV dataset in the `data` directory, supporting resume and refresh operations.

RELATIONSHIPS: This script relies on `fetch_emails.py` (specifically `fetch_unread_emails`, though it calls an unimported `fetch_unread_emails_safe` function) to interact with the Gmail API for email retrieval, and uses `pandas` for dataset persistence and `os` for file management. Serving as a dedicated data generation utility, its primary role is to create large, API-safe email datasets stored in the `../data/` directory. Other components of the codebase, such as machine learning models or analysis scripts, would then read and consume these pre-generated datasets rather than directly importing functions from this utility.

**Functions:**
- `create_bulk_dataset()`
- `fetch_unread_emails_safe()`
- `estimate_fetch_time()`

---

## 🌐 JavaScript Frontend Analysis

### 📄 `extension/background.js`

**AI Summary:** SUMMARY: This file serves as the Mailq extension's background service worker, orchestrating the authentication, fetching, classification, and labeling of unread emails when the extension icon is clicked.

RELATIONSHIPS: This file is the central orchestrator and event-driven entry point for the Mailq extension, directly depending on `config.js` for settings and various modules (`auth.js`, `gmail.js`, `classifier.js`, `utils.js`, `telemetry.js`) for core functionalities. It communicates classification results to active Gmail content scripts via `chrome.tabs.sendMessage`, which then depend on this script to receive the necessary data for display or further processing.

**Purpose:** Mailq Background Service Worker

**Characteristics:**
- Lines of code: 111
- Uses ES6 modules: ✅
- Contains async code: ✅
- Makes HTTP requests: ✅

**Imports:**
- `extension/config.js`
- `extension/modules/auth.js`
- `extension/modules/classifier.js`
- `extension/modules/gmail.js`
- `extension/modules/telemetry.js`
- *(+1 more)*

---

### 📄 `extension/config.js`

**AI Summary:** SUMMARY: This file centralizes configuration settings, API endpoints, operational limits, storage keys, and default user preferences for the Mailq browser extension.

RELATIONSHIPS: This file acts as a central configuration module, providing essential constants like API endpoints, storage keys, and operational limits used by the Mailq extension. The `extension/background.js` script explicitly imports and depends on these global parameters to manage background operations and settings, while this file itself has no external dependencies.

**Purpose:** Mailq Extension Configuration

**Characteristics:**
- Lines of code: 52
- Uses ES6 modules: ❌
- Contains async code: ❌
- Makes HTTP requests: ❌

---

### 📄 `extension/content.js`

**AI Summary:** SUMMARY: This content script injects into Gmail, monitoring email label changes, storing AI classifications received from the background script, and sending label corrections back if user-applied labels differ from predictions.

RELATIONSHIPS: This file acts as the interface between the extension's background script and the Gmail DOM. It depends on the `chrome.runtime` API to receive email classifications from the background script and sends user-initiated label corrections back to it. Its role is to inject functionality directly into Gmail, observing user interactions and providing real-time feedback to the extension's core classification logic.

**Purpose:** Content script for Gmail DOM monitoring

**Characteristics:**
- Lines of code: 100
- Uses ES6 modules: ✅
- Contains async code: ✅
- Makes HTTP requests: ❌

---

### 📄 `extension/modules/auth.js`

**AI Summary:** SUMMARY: This module handles Gmail OAuth authentication by providing functions to programmatically retrieve and revoke user access tokens for a Chrome extension.

RELATIONSHIPS: This file serves as an authentication utility, depending on the Chrome `identity` API to handle OAuth token acquisition and revocation. It is imported by `extension/background.js`, which likely uses these functions to manage the user's login state and access to Gmail services for the extension's operations.

**Purpose:** Gmail OAuth Authentication Module

**Characteristics:**
- Lines of code: 38
- Uses ES6 modules: ❌
- Contains async code: ✅
- Makes HTTP requests: ❌

---

### 📄 `extension/modules/budget.js`

**AI Summary:** SUMMARY: This file manages the extension's spend tracking and budget enforcement, allowing other parts of the application to check against a daily cap, record actual costs, and retrieve spending statistics.

RELATIONSHIPS: This module is central to the extension's spend tracking and budget enforcement, importing configuration details from `config.js` for limits and storage keys, and date utilities from `utils.js`. Other extension components depend on this file's exported functions (`checkSpendBudget`, `recordSpend`, `getSpendStats`) to enforce spending limits, log costs, and display financial statistics, persisting all data via `chrome.storage.local`.

**Purpose:** Spend Tracking & Budget Module

**Characteristics:**
- Lines of code: 80
- Uses ES6 modules: ✅
- Contains async code: ✅
- Makes HTTP requests: ❌

**Imports:**
- `extension/modules/../config.js`
- `extension/modules/utils.js`

---

### 📄 `extension/modules/cache.js`

**AI Summary:** SUMMARY: This module manages a local browser storage cache for email classification results, allowing retrieval of cached data and updates with new entries, while enforcing expiry and size limits.

RELATIONSHIPS: This utility module acts as a data caching layer. It explicitly depends on `extension/config.js` for critical settings like cache keys, expiry durations, and maximum entry limits, and relies on the `chrome.storage.local` API for its persistence. The `extension/modules/classifier.js` module imports this file, indicating it uses these caching functions to store its classification outcomes and retrieve previously processed email data, thereby reducing redundant classification requests.

**Purpose:** Classification Cache Module

**Characteristics:**
- Lines of code: 70
- Uses ES6 modules: ✅
- Contains async code: ✅
- Makes HTTP requests: ❌

**Imports:**
- `extension/modules/../config.js`

---

### 📄 `extension/modules/classifier.js`

**AI Summary:** SUMMARY: This module classifies emails by first checking a local cache, then sending unclassified emails (deduplicated by sender) to an external API, updating the cache with new classifications, and recording telemetry.

RELATIONSHIPS: This file acts as a core logic component for email classification, orchestrating interactions with an external Mailq API, a local caching mechanism (`cache.js`), and a telemetry system (`telemetry.js`). It depends on `config.js` for application-wide settings (e.g., API endpoints), and its primary `classifyEmails` function is imported and called by `extension/background.js` to perform classification tasks within the browser extension.

**Purpose:** Email Classification Module

**Characteristics:**
- Lines of code: 200
- Uses ES6 modules: ✅
- Contains async code: ✅
- Makes HTTP requests: ✅

**Imports:**
- `extension/modules/../config.js`
- `extension/modules/cache.js`
- `extension/modules/telemetry.js`

---

### 📄 `extension/modules/gmail.js`

**AI Summary:** SUMMARY: This file provides functions to interact with the Gmail API, primarily fetching and parsing a configurable number of unlabeled emails from the inbox, and managing Gmail labels.

RELATIONSHIPS: This module functions as the application's dedicated Gmail API layer, importing `CONFIG` from `../config.js` to determine operational parameters like `MAX_EMAILS`. It is a critical dependency for `extension/background.js`, which utilizes its exported functions to programmatically fetch, parse, and manage user emails and labels for the extension's core logic.

**Purpose:** Gmail API Operations Module

**Characteristics:**
- Lines of code: 224
- Uses ES6 modules: ✅
- Contains async code: ✅
- Makes HTTP requests: ✅

**Imports:**
- `extension/modules/../config.js`

---

### 📄 `extension/modules/notifications.js`

**AI Summary:** SUMMARY: This file provides utility functions to display Chrome browser notifications for success, error, and daily email/spend statistics within the Mailq extension.

RELATIONSHIPS: This file acts as a utility module for user feedback, abstracting the `chrome.notifications` API. It depends on the browser's `chrome.notifications` API for its core functionality and dynamically imports `getDailyReport` from `./telemetry.js` to display usage statistics. Other parts of the Mailq extension would call these exported functions (e.g., `showSuccess`, `showError`) to inform the user about operation outcomes or periodic updates.

**Purpose:** User Notifications Module

**Characteristics:**
- Lines of code: 35
- Uses ES6 modules: ✅
- Contains async code: ✅
- Makes HTTP requests: ❌

---

### 📄 `extension/modules/telemetry.js`

**AI Summary:** SUMMARY: This file manages the collection, storage, and reporting of daily telemetry data, including email classification counts, tier distribution, and associated costs, within the browser extension.

RELATIONSHIPS: This module acts as a utility layer, depending on `../config.js` for constants and dynamically importing `budget.js` for broader spend data, to manage the extension's operational metrics. It's imported by `background.js` and `classifier.js` to record email classification events and their associated costs. Its primary role is to track daily usage and provide statistical reports on the extension's activity and resource consumption.

**Purpose:** Telemetry Module

**Characteristics:**
- Lines of code: 120
- Uses ES6 modules: ✅
- Contains async code: ✅
- Makes HTTP requests: ❌

**Imports:**
- `extension/modules/../config.js`

---

### 📄 `extension/modules/utils.js`

**AI Summary:** SUMMARY: This file provides shared utility functions for extracting email domains, generating privacy-safe cache keys, managing user settings, and processing email lists within the extension.

RELATIONSHIPS: This file functions as a core utility module, exporting various helper functions used throughout the extension. Both `extension/background.js` and `extension/modules/budget.js` depend on it, importing functions to process emails (e.g., deduplicate, expand), generate secure cache keys, and retrieve user settings stored via `chrome.storage.local`.

**Purpose:** Shared Utility Functions

**Characteristics:**
- Lines of code: 106
- Uses ES6 modules: ❌
- Contains async code: ✅
- Makes HTTP requests: ❌

---

## 🔗 Dependency Graph

**File dependencies (who imports whom):**

```
api
  api_debug
  api_feedback
    api_dashboard
    feedback_manager
  api_organize
extension/background.js
memory_classifier
  mapper
  rules_engine
    logger
  vertex_gemini_classifier
    feedback_manager
extension/modules/classifier.js
```

## 🎯 Key Components Summary

**Orchestrator Files** (import many components):

- `mailq/api.py` - imports 7 internal modules
- `extension/background.js` - imports 6 internal modules
- `mailq/memory_classifier.py` - imports 3 internal modules
- `extension/modules/classifier.js` - imports 3 internal modules

**Core Classes** (with significant logic):

- `RulesEngine` in `mailq/rules_engine.py` - 13 methods
- `FeedbackManager` in `mailq/feedback_manager.py` - 11 methods
- `VertexGeminiClassifier` in `mailq/vertex_gemini_classifier.py` - 8 methods
- `CategoryManager` in `mailq/category_manager.py` - 7 methods
- `MemoryClassifier` in `mailq/memory_classifier.py` - 5 methods

---

## 📝 Analysis Complete

Use this report to understand:
- File purposes and responsibilities (with AI summaries!)
- Dependencies between components
- Key classes and their methods
- Entry points and orchestrators
