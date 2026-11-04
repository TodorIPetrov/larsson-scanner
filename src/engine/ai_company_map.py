"""
AI Company Map Engine (3 Scenarios of AI Dominance & Autonomy)
Based on Institutional Research "AI Stocks: What Everyone Is Missing" (3 November 2026):
- Scenario 01: Data-center AI dominates (Centralized cloud computing clusters)
- Scenario 02: Local AI dominates (On-device edge inference, PCs, phones, company servers)
- Scenario 03: Physical AI & autonomy (Robotics, mobile machines, autonomous driving)

Provides canonical scenario specs, status of listings, real-time breadth metrics,
cross-scenario All-Weather leader detection, and enriched payloads for dashboard & scanner.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# Complete Canonical Specification of the 3 AI Scenarios
AI_COMPANY_MAP_SPEC = [
    {
        "id": "scenario_01",
        "code": "S01",
        "title": "Data-center AI dominates",
        "title_bg": "Сценарий 01: Доминация на дейта-центровете (Cloud AI)",
        "subtitle": "Most inference runs in large, shared computing clusters.",
        "subtitle_bg": "По-голямата част от инференса се изпълнява в мащабни, споделени облачни изчислителни клъстери.",
        "theme_color": "#38bdf8",  # Sky blue accent
        "footer_note": "Qualitative order: business exposure, then category scale. Chinese examples grouped last. HK listings: Baidu 9888 · Alibaba 9988 · Tencent 0700 · Lenovo 0992.",
        "footer_note_bg": "Качествен ред: бизнес експозиция, след това мащаб на категорията. Китайските компании са групирани накрая. HK листинги: Baidu 9888 · Alibaba 9988 · Tencent 0700 · Lenovo 0992.",
        "categories": [
            {
                "id": "s01_cloud_infra",
                "name": "Cloud infrastructure",
                "name_bg": "Облачна инфраструктура",
                "benefit": "Rent computing capacity. Chinese examples add AI cloud infrastructure and enterprise services.",
                "benefit_bg": "Отдаване под наем на изчислителен капацитет (GPU cloud). Китайските примери добавят AI облачна инфраструктура и корпоративни услуги.",
                "companies": [
                    {"name": "CoreWeave", "ticker": "CRWV", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "Nebius", "ticker": "NBIS", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "SpaceX", "ticker": None, "alt_tickers": [], "status": "PRIVATE", "is_chinese": False, "note": "Частна компания (xAI compute / Starlink)"},
                    {"name": "Oracle", "ticker": "ORCL", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "Microsoft", "ticker": "MSFT", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "Alphabet", "ticker": "GOOGL", "alt_tickers": ["GOOG", "ABEC.DE"], "status": "LISTED", "is_chinese": False},
                    {"name": "Amazon", "ticker": "AMZN", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "Baidu", "ticker": "BIDU", "alt_tickers": ["9888.HK"], "status": "LISTED", "is_chinese": True},
                    {"name": "Alibaba", "ticker": "BABA", "alt_tickers": ["9988.HK"], "status": "LISTED", "is_chinese": True},
                    {"name": "Tencent", "ticker": "0700.HK", "alt_tickers": [], "status": "LISTED", "is_chinese": True},
                ],
            },
            {
                "id": "s01_models_platforms",
                "name": "Models & AI platforms",
                "name_bg": "Модели & AI платформи",
                "benefit": "Sell models and AI services. Chinese model families: ERNIE (Baidu), Qwen (Alibaba) and Hy (Tencent).",
                "benefit_bg": "Продажба на Foundation модели и AI API услуги. Китайски моделни семейства: ERNIE (Baidu), Qwen (Alibaba) и Hunyuan/Hy (Tencent).",
                "companies": [
                    {"name": "Anthropic", "ticker": None, "alt_tickers": [], "status": "PRIVATE", "is_chinese": False, "note": "Частна компания (Claude моделно семейство)"},
                    {"name": "OpenAI", "ticker": None, "alt_tickers": [], "status": "PRIVATE", "is_chinese": False, "note": "Частна компания (GPT / o-series модели)"},
                    {"name": "SpaceX", "ticker": None, "alt_tickers": [], "status": "PRIVATE", "is_chinese": False, "note": "Частна компания (xAI / Grok интеграция)"},
                    {"name": "Microsoft", "ticker": "MSFT", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "Alphabet", "ticker": "GOOGL", "alt_tickers": ["GOOG", "ABEC.DE"], "status": "LISTED", "is_chinese": False},
                    {"name": "Baidu", "ticker": "BIDU", "alt_tickers": ["9888.HK"], "status": "LISTED", "is_chinese": True},
                    {"name": "Alibaba", "ticker": "BABA", "alt_tickers": ["9988.HK"], "status": "LISTED", "is_chinese": True},
                    {"name": "Tencent", "ticker": "0700.HK", "alt_tickers": [], "status": "LISTED", "is_chinese": True},
                ],
            },
            {
                "id": "s01_accelerators_chips",
                "name": "Accelerators & custom AI chips",
                "name_bg": "Ускорители & специализирани AI чипове",
                "benefit": "Supply GPUs and specialized processors for large-scale training and inference.",
                "benefit_bg": "Доставка на водещи GPU и специализирани ASIC процесори за мащабно обучение и дейта-център инференс.",
                "companies": [
                    {"name": "NVIDIA", "ticker": "NVDA", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "Broadcom", "ticker": "AVGO", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "AMD", "ticker": "AMD", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                ],
            },
            {
                "id": "s01_dc_networking",
                "name": "Data-center networking",
                "name_bg": "Дейта-център мрежово оборудване",
                "benefit": "Connect large numbers of accelerators with high-speed networks.",
                "benefit_bg": "Свързване на огромен брой GPU ускорители чрез ултра-високоскоростни Ethernet и InfiniBand мрежи.",
                "companies": [
                    {"name": "Arista Networks", "ticker": "ANET", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "Broadcom", "ticker": "AVGO", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "NVIDIA", "ticker": "NVDA", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                ],
            },
            {
                "id": "s01_chip_mfg_packaging",
                "name": "Chip manufacturing & advanced packaging",
                "name_bg": "Производство на чипове & усъвършенствано пакетиране",
                "benefit": "Manufacture advanced processors and provide packaging for AI systems.",
                "benefit_bg": "Производство на процесори по най-авангардни нанометрови литографии и 2.5D/3D пакетиране (CoWoS) за AI системи.",
                "companies": [
                    {"name": "TSMC", "ticker": "TSM", "alt_tickers": ["2330.TW"], "status": "LISTED", "is_chinese": False},
                ],
            },
            {
                "id": "s01_memory_storage",
                "name": "Memory & storage",
                "name_bg": "Памет & сторидж",
                "benefit": "Supply high-bandwidth memory, server memory and storage.",
                "benefit_bg": "Доставка на High-Bandwidth Memory (HBM3e/HBM4), DDR5 сървърна памет и enterprise SSD хранилища.",
                "companies": [
                    {"name": "SK hynix", "ticker": "000660.KS", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "Micron", "ticker": "MU", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "Samsung", "ticker": "005930.KS", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                ],
            },
            {
                "id": "s01_semi_equipment",
                "name": "Semiconductor equipment",
                "name_bg": "Полупроводниково оборудване",
                "benefit": "Supply equipment to expand and upgrade semiconductor manufacturing.",
                "benefit_bg": "Доставка на оборудване за разширяване и технологично модернизиране на полупроводниковите фабрики.",
                "companies": [
                    {"name": "ASML", "ticker": "ASML", "alt_tickers": ["ASML.AS"], "status": "LISTED", "is_chinese": False},
                    {"name": "Applied Materials", "ticker": "AMAT", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "Lam Research", "ticker": "LRCX", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "KLA", "ticker": "KLAC", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                ],
            },
            {
                "id": "s01_servers_systems",
                "name": "Servers & systems",
                "name_bg": "Сървъри & клъстерни системи",
                "benefit": "Build and integrate computing infrastructure for cloud operators and enterprises.",
                "benefit_bg": "Проектиране, изграждане и интеграция на сървърна инфраструктура за hyperscale облачни оператори и корпорации.",
                "companies": [
                    {"name": "Supermicro", "ticker": "SMCI", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "Dell", "ticker": "DELL", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "HPE", "ticker": "HPE", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "Lenovo", "ticker": "0992.HK", "alt_tickers": [], "status": "LISTED", "is_chinese": True},
                ],
            },
            {
                "id": "s01_power_cooling",
                "name": "Power, cooling & energy storage",
                "name_bg": "Енергия, охлаждане & батерийно съхранение",
                "benefit": "Provide cooling, electrical equipment and battery storage for large computing sites.",
                "benefit_bg": "Течно и прецизно охлаждане, електрическо трансформаторно оборудване и батерийно съхранение (BESS) за AI клъстери.",
                "companies": [
                    {"name": "Vertiv", "ticker": "VRT", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "Schneider Electric", "ticker": "SU.PA", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "Eaton", "ticker": "ETN", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "Tesla", "ticker": "TSLA", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                ],
            },
            {
                "id": "s01_internal_training",
                "name": "Training for own products",
                "name_bg": "Обучение за собствени крайни продукти",
                "benefit": "Internal training: strategic dependence, not training revenue. Tencent and Alibaba add ads and commerce.",
                "benefit_bg": "Вътрешно AI обучение: стратегическа зависимост за собствените платформи, без директни приходи от отдаване. Tencent и Alibaba добавят реклами и е-търговия.",
                "companies": [
                    {"name": "Tesla", "ticker": "TSLA", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "Meta", "ticker": "META", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "Alphabet", "ticker": "GOOGL", "alt_tickers": ["GOOG", "ABEC.DE"], "status": "LISTED", "is_chinese": False},
                    {"name": "Tencent", "ticker": "0700.HK", "alt_tickers": [], "status": "LISTED", "is_chinese": True},
                    {"name": "Alibaba", "ticker": "BABA", "alt_tickers": ["9988.HK"], "status": "LISTED", "is_chinese": True},
                ],
            },
        ],
    },
    {
        "id": "scenario_02",
        "code": "S02",
        "title": "Local AI dominates",
        "title_bg": "Сценарий 02: Доминация на локалния AI (On-Device & Edge)",
        "subtitle": "Most inference runs on personal devices, workstations and company-owned machines.",
        "subtitle_bg": "По-голямата част от инференса се изпълнява на персонални устройства, работни станции и локални сървъри.",
        "theme_color": "#eab308",  # Amber gold accent
        "footer_note": "Qualitative order: business exposure, then category scale. Chinese examples grouped last. HK listings: Lenovo 0992 · Xiaomi 1810 · Alibaba 9988. Training can remain centralized in either scenario. Listing access depends on your broker.",
        "footer_note_bg": "Качествен ред: бизнес експозиция, след това мащаб на категорията. Китайските компании са групирани накрая. HK листинги: Lenovo 0992 · Xiaomi 1810 · Alibaba 9988. Обучението може да остане централизирано и при двата сценария.",
        "categories": [
            {
                "id": "s02_premium_pcs_devices",
                "name": "Premium computers & personal devices",
                "name_bg": "Премиум компютри & персонални устройства",
                "benefit": "Sell more capable devices and larger memory options. Lenovo adds PCs; Xiaomi adds phones and tablets.",
                "benefit_bg": "Продажба на по-мощни крайни устройства и по-високи конфигурации с памет (AI PC / Edge). Lenovo добавя PC; Xiaomi добавя телефони и таблети.",
                "companies": [
                    {"name": "Apple", "ticker": "AAPL", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "HP Inc.", "ticker": "HPQ", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "Dell", "ticker": "DELL", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "Samsung", "ticker": "005930.KS", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "Lenovo", "ticker": "0992.HK", "alt_tickers": [], "status": "LISTED", "is_chinese": True},
                    {"name": "Xiaomi", "ticker": "1810.HK", "alt_tickers": [], "status": "LISTED", "is_chinese": True},
                ],
            },
            {
                "id": "s02_pc_processors",
                "name": "PC processors & integrated AI chips",
                "name_bg": "PC процесори & вградени AI чипове (NPU)",
                "benefit": "Add AI compute to PCs. Apple is assessed through Mac exposure; its chips are not sold separately.",
                "benefit_bg": "Интеграция на NPU изчислителна мощност в персоналните компютри. Apple се оценява чрез Mac продажбите; чиповете Apple Silicon не се продават отделно.",
                "companies": [
                    {"name": "Intel", "ticker": "INTC", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "AMD", "ticker": "AMD", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "Apple", "ticker": "AAPL", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "Qualcomm", "ticker": "QCOM", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                ],
            },
            {
                "id": "s02_local_gpus_workstations",
                "name": "Local GPUs & AI workstations",
                "name_bg": "Локални клиентски GPU & AI работни станции",
                "benefit": "Client GPU/APU suppliers, then workstation vendors. Local AI revenue is not separately disclosed.",
                "benefit_bg": "Доставчици на клиентски GPU/APU, следвани от вендори на работни станции. Приходите от локален AI не се оповестяват отделно.",
                "companies": [
                    {"name": "AMD", "ticker": "AMD", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "NVIDIA", "ticker": "NVDA", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "HP Inc.", "ticker": "HPQ", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "Dell", "ticker": "DELL", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "Lenovo", "ticker": "0992.HK", "alt_tickers": [], "status": "LISTED", "is_chinese": True},
                ],
            },
            {
                "id": "s02_smartphone_processors",
                "name": "Smartphone & tablet processors",
                "name_bg": "Процесори за смартфони & таблети",
                "benefit": "Run AI on phones and tablets. Apple and Xiaomi use their own processors inside their devices.",
                "benefit_bg": "Локален AI инференс на мобилни устройства. Apple и Xiaomi използват собствени/оптимизирани чипсети в устройствата си.",
                "companies": [
                    {"name": "Qualcomm", "ticker": "QCOM", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "MediaTek", "ticker": "2454.TW", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "Apple", "ticker": "AAPL", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "Alphabet", "ticker": "GOOGL", "alt_tickers": ["GOOG", "ABEC.DE"], "status": "LISTED", "is_chinese": False, "note": "Tensor G-чипове в Pixel и мобилен Gemini Nano в Android (NASDAQ: GOOGL)"},
                    {"name": "Samsung", "ticker": "005930.KS", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "Xiaomi", "ticker": "1810.HK", "alt_tickers": [], "status": "LISTED", "is_chinese": True},
                ],
            },
            {
                "id": "s02_local_memory_storage",
                "name": "Memory & storage",
                "name_bg": "Памет & сторидж за крайни устройства",
                "benefit": "Equip each device to store and run its own models. DRAM, LPDDR and storage gain importance.",
                "benefit_bg": "Оборудване на всяко крайно устройство да съхранява и изпълнява локални модели. DRAM, LPDDR5X и бързият сторидж придобиват решаваща роля.",
                "companies": [
                    {"name": "Micron", "ticker": "MU", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "SK hynix", "ticker": "000660.KS", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "Samsung", "ticker": "005930.KS", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                ],
            },
            {
                "id": "s02_local_chip_mfg",
                "name": "Chip manufacturing",
                "name_bg": "Производство на чипове (Foundry)",
                "benefit": "Produce processors for competing device makers. Samsung exposure includes its foundry business.",
                "benefit_bg": "Производство на чипове за конкурентни брандове крайни устройства. Експозицията на Samsung включва нейния леярен (foundry) бизнес.",
                "companies": [
                    {"name": "TSMC", "ticker": "TSM", "alt_tickers": ["2330.TW"], "status": "LISTED", "is_chinese": False},
                    {"name": "Samsung", "ticker": "005930.KS", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                ],
            },
            {
                "id": "s02_local_semi_equipment",
                "name": "Semiconductor equipment",
                "name_bg": "Полупроводниково оборудване",
                "benefit": "Benefit if local AI increases total chip production and manufacturing complexity.",
                "benefit_bg": "Печели от нарастване на общия брой произведени клиентски чипове и технологичната им сложност.",
                "companies": [
                    {"name": "ASML", "ticker": "ASML", "alt_tickers": ["ASML.AS"], "status": "LISTED", "is_chinese": False},
                    {"name": "Applied Materials", "ticker": "AMAT", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "Lam Research", "ticker": "LRCX", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "KLA", "ticker": "KLAC", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                ],
            },
            {
                "id": "s02_company_ai_servers",
                "name": "Company-owned AI servers",
                "name_bg": "Собствени корпоративни AI сървъри",
                "benefit": "Install shared inference systems in offices and private facilities.",
                "benefit_bg": "Инсталация на споделени локални AI инференс системи в офиси и частни корпоративни съоръжения (on-prem).",
                "companies": [
                    {"name": "Supermicro", "ticker": "SMCI", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "Dell", "ticker": "DELL", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "HPE", "ticker": "HPE", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "NVIDIA", "ticker": "NVDA", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "Lenovo", "ticker": "0992.HK", "alt_tickers": [], "status": "LISTED", "is_chinese": True},
                ],
            },
            {
                "id": "s02_enterprise_deployment_sw",
                "name": "Enterprise deployment software",
                "name_bg": "Софтуер за корпоративно внедряване",
                "benefit": "Manage private AI deployments. IBM includes Red Hat; Alibaba includes on-premises Apsara Stack.",
                "benefit_bg": "Управление и оркестрация на частни AI внедрявания. IBM включва Red Hat OpenShift; Alibaba включва локалния Apsara Stack.",
                "companies": [
                    {"name": "IBM", "ticker": "IBM", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "Microsoft", "ticker": "MSFT", "alt_tickers": [], "status": "LISTED", "is_chinese": False},
                    {"name": "Alphabet", "ticker": "GOOGL", "alt_tickers": ["GOOG", "ABEC.DE"], "status": "LISTED", "is_chinese": False, "note": "Google Workspace Gemini & Android Enterprise локални агенти (NASDAQ: GOOGL)"},
                    {"name": "Alibaba", "ticker": "BABA", "alt_tickers": ["9988.HK"], "status": "LISTED", "is_chinese": True},
                ],
            },
        ],
    },
    {
        "id": "scenario_03",
        "code": "S03",
        "title": "Physical AI & autonomy",
        "title_bg": "Сценарий 03: Физически AI & Автономия (Robotics & Embodied AI)",
        "subtitle": "Robotics and autonomous machines, powered by AI that acts in the physical world.",
        "subtitle_bg": "Роботика и автономни машини, задвижвани от AI модели, взаимодействащи с физическия свят.",
        "theme_color": "#10b981",  # Emerald / Mint green accent
        "footer_note": "Chinese companies grouped last. Robots can combine onboard inference with centralized training and simulation. Listing status as of 3 November 2026. Sources: company disclosures and exchange notices.",
        "footer_note_bg": "Китайските компании са групирани накрая. Роботите комбинират локален инференс на борда с централизирано обучение и симулация в облак. Статус на листингите към 3 ноември 2026.",
        "categories": [
            {
                "id": "s03_humanoid_mobile_robots",
                "name": "Humanoid & mobile robots",
                "name_bg": "Хуманоидни & мобилни роботи",
                "benefit": "Develop robots for industrial, commercial and consumer use, including household tasks.",
                "benefit_bg": "Разработка на хуманоидни и мобилни роботи за индустриални, логистични, търговски и битови задачи.",
                "listing_details": "Listed: Tesla (NASDAQ: TSLA), UBTECH (HK: 9880). Listing pending: Agility Robotics via CCXI. AGLT expected 5 Nov 2026, subject to closing. Privately held: Figure, Apptronik and AGIBOT. Boston Dynamics: unlisted subsidiary, Hyundai group-owned. Unitree: Shanghai STAR 688836. Stock Connect access is limited to institutional professional investors.",
                "companies": [
                    {"name": "Tesla", "ticker": "TSLA", "alt_tickers": [], "status": "LISTED", "is_chinese": False, "note": "Optimus хуманоиден робот (NASDAQ: TSLA)"},
                    {"name": "Agility Robotics", "ticker": "CCXI", "alt_tickers": ["AGLT"], "status": "PENDING_IPO", "is_chinese": False, "note": "Digit робот; листване чрез CCXI / AGLT очаквано на 5 ноември 2026"},
                    {"name": "Figure", "ticker": None, "alt_tickers": [], "status": "PRIVATE", "is_chinese": False, "note": "Figure 02 робот; частна компания (партньор на OpenAI / BMW)"},
                    {"name": "Apptronik", "ticker": None, "alt_tickers": [], "status": "PRIVATE", "is_chinese": False, "note": "Apollo хуманоид; частна компания (партньор на Mercedes-Benz)"},
                    {"name": "Boston Dynamics", "ticker": "005380.KS", "alt_tickers": [], "status": "UNLISTED_SUBSIDIARY", "is_chinese": False, "note": "Atlas & Spot; нелистнато дъщерно дружество, собственост на Hyundai Motor"},
                    {"name": "Unitree", "ticker": "688836.SS", "alt_tickers": [], "status": "STAR_INSTITUTIONAL", "is_chinese": True, "note": "G1 / H1 хуманоиди & кучета; Shanghai STAR 688836 (Stock Connect институционален)"},
                    {"name": "AGIBOT", "ticker": None, "alt_tickers": [], "status": "PRIVATE", "is_chinese": True, "note": "Zhiyuan Expedition A1/A2 хуманоиди; частна компания (Китай)"},
                    {"name": "UBTECH", "ticker": "9880.HK", "alt_tickers": [], "status": "LISTED", "is_chinese": True, "note": "Walker S хуманоид за автомобилни заводи (HKEX: 9880)"},
                ],
            },
            {
                "id": "s03_industrial_cobots",
                "name": "Industrial & collaborative robots",
                "name_bg": "Индустриални & колаборативни роботи (Cobots)",
                "benefit": "Automate factory work and material handling. Teradyne owns Universal Robots and MiR.",
                "benefit_bg": "Автоматизация на заводски поточни линии, заваряване и логистичен транспорт. Teradyne притежава Universal Robots и MiR.",
                "listing_details": "Listed: FANUC (Tokyo: 6954), Teradyne (NASDAQ: TER). Teradyne owns Universal Robots and MiR.",
                "companies": [
                    {"name": "FANUC", "ticker": "6954.T", "alt_tickers": [], "status": "LISTED", "is_chinese": False, "note": "Световен лидер в CNC машини и индустриални роботи (Tokyo: 6954)"},
                    {"name": "Teradyne", "ticker": "TER", "alt_tickers": [], "status": "LISTED", "is_chinese": False, "note": "Собственик на Universal Robots (cobots) и MiR (NASDAQ: TER)"},
                ],
            },
            {
                "id": "s03_robotics_compute",
                "name": "Robotics computing platforms",
                "name_bg": "Изчислителни платформи за роботика",
                "benefit": "Supply onboard AI compute, simulation and training platforms for robot developers.",
                "benefit_bg": "Доставка на бордови чипове (Jetson Thor), физически симулатори (Omniverse Isaac Sim) и базови модели (GR00T) за роботика.",
                "listing_details": "Listed: NVIDIA (NASDAQ: NVDA).",
                "companies": [
                    {"name": "NVIDIA", "ticker": "NVDA", "alt_tickers": [], "status": "LISTED", "is_chinese": False, "note": "Project GR00T, Jetson Thor, Isaac Sim роботика (NASDAQ: NVDA)"},
                    {"name": "TSMC", "ticker": "TSM", "alt_tickers": ["2330.TW"], "status": "LISTED", "is_chinese": False, "note": "Водеща леярна за всички роботика/автономни чипове: NVIDIA Thor, Tesla FSD HW4/5 (NYSE: TSM)"},
                    {"name": "ASML", "ticker": "ASML", "alt_tickers": ["ASML.AS"], "status": "LISTED", "is_chinese": False, "note": "Монополно литографско оборудване за авангардните полупроводници за автономност (NASDAQ: ASML)"},
                ],
            },
            {
                "id": "s03_autonomous_driving",
                "name": "Autonomous driving",
                "name_bg": "Автономно шофиране & Роботаксита",
                "benefit": "Develop driving systems, robotaxis and vehicle AI chips. Alphabet includes Waymo. Horizon supplies chips. Baidu operates Apollo Go.",
                "benefit_bg": "Разработка на системи за автономно шофиране (FSD), роботакси флотилии и автомобилни AI процесори. Alphabet включва Waymo; Horizon доставя чипове; Baidu оперира Apollo Go.",
                "listing_details": "Listed: Tesla (NASDAQ: TSLA), Alphabet (NASDAQ: GOOGL / GOOG), Horizon Robotics (HK: 9660), Baidu (NASDAQ: BIDU / HK: 9888). Alphabet includes Waymo. Horizon supplies chips. Baidu operates Apollo Go robotaxis.",
                "companies": [
                    {"name": "Tesla", "ticker": "TSLA", "alt_tickers": [], "status": "LISTED", "is_chinese": False, "note": "Full Self-Driving (FSD) & Cybercab Robotaxi (NASDAQ: TSLA)"},
                    {"name": "Alphabet", "ticker": "GOOGL", "alt_tickers": ["GOOG", "ABEC.DE"], "status": "LISTED", "is_chinese": False, "note": "Waymo лидер в търговските роботакси услуги (NASDAQ: GOOGL)"},
                    {"name": "Horizon Robotics", "ticker": "9660.HK", "alt_tickers": [], "status": "LISTED", "is_chinese": True, "note": "Journey AI чипове за автономно шофиране в Китай (HKEX: 9660)"},
                    {"name": "Baidu", "ticker": "BIDU", "alt_tickers": ["9888.HK"], "status": "LISTED", "is_chinese": True, "note": "Apollo Go най-голямата роботакси мрежа в Китай (NASDAQ: BIDU / HK: 9888)"},
                ],
            },
        ],
    },
]


def get_ticker_ai_scenarios(ticker: Optional[str]) -> List[str]:
    """
    Returns list of scenarios ['S01', 'S02', 'S03'] where a given ticker participates.
    Matches primary ticker and alt_tickers.
    """
    if not ticker:
        return []
    clean = ticker.strip().upper()
    scenarios = set()

    for sc in AI_COMPANY_MAP_SPEC:
        sc_code = sc["code"]
        for cat in sc["categories"]:
            for comp in cat["companies"]:
                p_tick = (comp.get("ticker") or "").upper()
                alts = [a.upper() for a in comp.get("alt_tickers", [])]
                if clean == p_tick or clean in alts:
                    scenarios.add(sc_code)

    return sorted(list(scenarios))


def build_ai_company_map_payload(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Enriches the AI Company Map with live scanner states, fundamentals, and Smart Money flows.
    Returns:
    - scenarios: enriched list of scenarios and categories
    - breadth_summary: per-scenario metrics (% GOLD, % BLUE, average RS, top leader)
    - all_weather_leaders: list of cross-scenario companies that win in 2 or 3 scenarios
    """
    items_map: Dict[str, Dict[str, Any]] = {}
    for it in items:
        sym = (it.get("ticker") or "").upper()
        if sym:
            items_map[sym] = it

    enriched_scenarios = []
    cross_scenario_counts: Dict[str, Dict[str, Any]] = {}

    for sc in AI_COMPANY_MAP_SPEC:
        sc_code = sc["code"]
        sc_gold = 0
        sc_blue = 0
        sc_neutral = 0
        sc_total_listed = 0
        rs_scores = []
        sm_scores = []
        fresh_gold_flips = 0
        leaders_pool = []

        enriched_categories = []
        for cat in sc["categories"]:
            enriched_companies = []
            cat_gold = 0
            cat_total_listed = 0

            for comp in cat["companies"]:
                p_tick = (comp.get("ticker") or "").upper()
                alts = [a.upper() for a in comp.get("alt_tickers", [])]

                # Match with market item
                live_item = items_map.get(p_tick)
                if not live_item:
                    for alt in alts:
                        if alt in items_map:
                            live_item = items_map[alt]
                            break

                comp_dict = dict(comp)
                if live_item:
                    st = live_item.get("state", "NEUTRAL")
                    price = live_item.get("price")
                    rs = live_item.get("rs_rating", 50)
                    tier = live_item.get("empirical_tier", "B")
                    is_flip = bool(live_item.get("is_gold_flip", False))
                    bars_flip = live_item.get("bars_since_flip")
                    fund = live_item.get("fundamental") or {}
                    sm = live_item.get("smart_money") or {}

                    comp_dict.update({
                        "has_live_data": True,
                        "ticker": live_item.get("ticker", p_tick),
                        "tv_symbol": live_item.get("tv_symbol"),
                        "tv_url": f"https://www.tradingview.com/chart/?symbol={live_item.get('tv_symbol')}&interval=1D",
                        "state": st,
                        "price": price,
                        "spread_pct": live_item.get("spread_pct"),
                        "rs_rating": rs,
                        "empirical_tier": tier,
                        "is_gold_flip": is_flip,
                        "bars_since_flip": bars_flip,
                        "fair_value": fund.get("fair_value"),
                        "mos_pct": fund.get("mos_pct"),
                        "moat": fund.get("moat", "None"),
                        "z_score": fund.get("z_score"),
                        "m_score": fund.get("m_score"),
                        "verdict": fund.get("verdict", "FAIRLY VALUED"),
                        "smart_money_score": sm.get("smart_money_score"),
                        "flow_label_bg": sm.get("flow_label_bg"),
                    })

                    cat_total_listed += 1
                    sc_total_listed += 1
                    if st == "GOLD":
                        cat_gold += 1
                        sc_gold += 1
                        if is_flip:
                            fresh_gold_flips += 1
                    elif st == "BLUE":
                        sc_blue += 1
                    else:
                        sc_neutral += 1

                    if rs is not None:
                        rs_scores.append(float(rs))
                    if sm.get("smart_money_score") is not None:
                        sm_scores.append(float(sm["smart_money_score"]))

                    leaders_pool.append({
                        "name": comp["name"],
                        "ticker": live_item.get("ticker", p_tick),
                        "state": st,
                        "rs_rating": rs,
                        "price": price,
                        "mos_pct": fund.get("mos_pct"),
                    })

                    # Track cross-scenario exposure
                    c_key = comp["name"]
                    if c_key not in cross_scenario_counts:
                        cross_scenario_counts[c_key] = {
                            "name": comp["name"],
                            "ticker": live_item.get("ticker", p_tick),
                            "tv_symbol": live_item.get("tv_symbol"),
                            "status": comp.get("status"),
                            "scenarios": set(),
                            "categories": [],
                            "live_item": comp_dict,
                        }
                    cross_scenario_counts[c_key]["scenarios"].add(sc_code)
                    cross_scenario_counts[c_key]["categories"].append(cat["name"])

                else:
                    comp_dict.update({
                        "has_live_data": False,
                        "state": "UNTRACKED",
                        "price": None,
                        "rs_rating": None,
                    })

                enriched_companies.append(comp_dict)

            cat_dict = dict(cat)
            cat_dict["companies"] = enriched_companies
            cat_dict["total_listed"] = cat_total_listed
            cat_dict["gold_count"] = cat_gold
            cat_dict["gold_pct"] = round((cat_gold / cat_total_listed * 100.0), 1) if cat_total_listed > 0 else 0.0
            enriched_categories.append(cat_dict)

        # Sort leaders
        leaders_pool.sort(key=lambda x: (x["state"] == "GOLD", x["rs_rating"] or 0), reverse=True)
        top_leader = leaders_pool[0] if leaders_pool else None

        gold_pct = round((sc_gold / sc_total_listed * 100.0), 1) if sc_total_listed > 0 else 0.0
        blue_pct = round((sc_blue / sc_total_listed * 100.0), 1) if sc_total_listed > 0 else 0.0
        neutral_pct = round((sc_neutral / sc_total_listed * 100.0), 1) if sc_total_listed > 0 else 0.0
        avg_rs = round(sum(rs_scores) / len(rs_scores), 1) if rs_scores else 50.0
        avg_sm = round(sum(sm_scores) / len(sm_scores), 1) if sm_scores else 50.0

        sc_dict = dict(sc)
        sc_dict["categories"] = enriched_categories
        sc_dict["metrics"] = {
            "total_listed": sc_total_listed,
            "gold_count": sc_gold,
            "blue_count": sc_blue,
            "neutral_count": sc_neutral,
            "gold_pct": gold_pct,
            "blue_pct": blue_pct,
            "neutral_pct": neutral_pct,
            "avg_rs_rating": avg_rs,
            "avg_smart_money": avg_sm,
            "fresh_gold_flips": fresh_gold_flips,
            "top_leader": top_leader,
        }
        enriched_scenarios.append(sc_dict)

    # Format All-Weather Cross-Scenario Leaders
    all_weather = []
    for c_key, data in cross_scenario_counts.items():
        sc_list = sorted(list(data["scenarios"]))
        if len(sc_list) >= 2:
            live = data["live_item"]
            all_weather.append({
                "name": data["name"],
                "ticker": data["ticker"],
                "tv_symbol": data.get("tv_symbol"),
                "status": data["status"],
                "scenarios": sc_list,
                "scenario_count": len(sc_list),
                "categories": data["categories"],
                "state": live.get("state", "NEUTRAL"),
                "price": live.get("price"),
                "rs_rating": live.get("rs_rating"),
                "empirical_tier": live.get("empirical_tier", "B"),
                "mos_pct": live.get("mos_pct"),
                "moat": live.get("moat", "None"),
                "smart_money_score": live.get("smart_money_score"),
                "flow_label_bg": live.get("flow_label_bg"),
            })

    # Sort all-weather: 3 scenarios first, then highest RS rating and GOLD state
    all_weather.sort(key=lambda x: (x["scenario_count"], x["state"] == "GOLD", x["rs_rating"] or 0), reverse=True)

    return {
        "title": "AI Company Map (3 Scenarios)",
        "subtitle": "Data-Center AI dominates · Local AI dominates · Physical AI & Autonomy",
        "scenarios": enriched_scenarios,
        "all_weather_leaders": all_weather,
        "scenarios_breadth": {
            sc["code"]: sc["metrics"] for sc in enriched_scenarios
        },
    }
