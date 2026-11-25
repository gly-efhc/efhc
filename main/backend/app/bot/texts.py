"""Localized Telegram bot UI texts for EFHC.

This module is the backend/bot text contour.  It is intentionally
kept small and explicit because bot messages are trust-sensitive.
Supported call styles:
- t("help")
- t("ru", "help")
Fallback language: Russian, then English, then key.
"""

from __future__ import annotations

import string
from typing import Any

BOT_TEXT_KEYS: tuple[str, ...] = (
    "welcome",
    "menu",
    "no_access",
    "help",
    "subscribe.required",
    "panels.summary",
    "profile.header",
    "profile.lines",
    "exchange.preview",
    "ranks.me",
    "ranks.top.header",
    "ranks.top.line",
    "referrals.header",
    "referrals.active.count",
    "referrals.inactive.count",
    "tasks.submitted",
    "admin.entry",
    "admin.hub.entry",
    "faq.entry",
)

BOT_TEXT_LANGS: tuple[str, ...] = (
    "en",
    "ru",
    "uk",
    "de",
    "fr",
    "es",
    "it",
    "pl",
    "tr",
    "da",
    "hi",
    "id",
    "sw",
    "pt",
    "ko",
    "ja",
)

TEXTS: dict[str, dict[str, str]] = {
    "en": {
        "welcome": (
            "Hi, {username}! ⚡\n"
            "VIP: {vip_flag}\n"
            "Panels: {panels}\n"
            "Available kWh: {avail_kwh}"
        ),
        "menu": "Main menu",
        "no_access": "⛔ Access denied.",
        "help": (
            "EFHC Bot is the navigation layer for the WebApp.\n\n"
            "Main commands:\n"
            "/start — open main menu\n"
            "/help — quick help\n"
            "/hub — open Hub\n"
            "/faq — open FAQ\n"
            "/panels — panels summary\n"
            "/profile — profile\n"
            "/balance — balance\n"
            "/tasks — tasks\n"
            "/referrals — referrals\n"
            "/ranks — ranks\n"
            "/withdraw — withdrawal\n"
            "/webapp — open Mini App\n\n"
            "FAQ: 20 sections / 250 questions and answers.\n"
            "Hub is the project navigation layer."
        ),
        "subscribe.required": ("Subscribe to {channel} to continue."),
        "panels.summary": (
            "⚡ Panels\n"
            "Active: {count}\n"
            "Per second: {per_sec} kWh\n"
            "Available: {avail_kwh} kWh"
        ),
        "profile.header": "👤 Profile",
        "profile.lines": (
            "tg_id: {tg_id}\n"
            "VIP: {vip_flag}\n"
            "Active panels: {panels}\n"
            "Available kWh: {avail_kwh}\n"
            "Total generated kWh: {total_kwh}"
        ),
        "exchange.preview": ("🔁 Exchange: {kwh} kWh → {efhc} EFHC"),
        "ranks.me": "🏆 Your rank: #{rank} · {total_kwh} kWh",
        "ranks.top.header": "Top {limit}",
        "ranks.top.line": "#{rank} {username} — {total_kwh} kWh",
        "referrals.header": "👥 Referrals",
        "referrals.active.count": "Active: {count}",
        "referrals.inactive.count": "Inactive: {count}",
        "tasks.submitted": "🎯 Tasks",
        "admin.entry": "🛠 Open Admin Hub in WebApp below.",
        "admin.hub.entry": (
            "🧭 Hub management is available via Admin Hub in WebApp."
        ),
        "faq.entry": (
            "❓ Open FAQ in WebApp using the button below.\n"
            "Current FAQ inventory: 20 sections / 250 Q&A."
        ),
    },
    "ru": {
        "welcome": (
            "Привет, {username}! ⚡\n"
            "VIP: {vip_flag}\n"
            "Панели: {panels}\n"
            "Доступно kWh: {avail_kwh}"
        ),
        "menu": "Главное меню",
        "no_access": "⛔ Нет доступа.",
        "help": (
            "EFHC Bot — навигация к разделам WebApp.\n\n"
            "Основные команды:\n"
            "/start — открыть главное меню\n"
            "/help — краткая справка\n"
            "/hub — открыть Hub\n"
            "/faq — открыть FAQ\n"
            "/panels — сводка по панелям\n"
            "/profile — профиль\n"
            "/balance — баланс\n"
            "/tasks — задания\n"
            "/referrals — рефералы\n"
            "/ranks — ранги\n"
            "/withdraw — вывод\n"
            "/webapp — открыть Mini App\n\n"
            "FAQ: 20 разделов / 250 вопросов и ответов.\n"
            "Hub — навигационный слой проекта."
        ),
        "subscribe.required": (
            "Для доступа нужна подписка на канал {channel}."
        ),
        "panels.summary": (
            "⚡ Панели\n"
            "Активно: {count}\n"
            "Генерация в сек.: {per_sec} kWh\n"
            "Доступно: {avail_kwh} kWh"
        ),
        "profile.header": "👤 Профиль",
        "profile.lines": (
            "tg_id: {tg_id}\n"
            "VIP: {vip_flag}\n"
            "Активных панелей: {panels}\n"
            "Доступно kWh: {avail_kwh}\n"
            "Всего сгенерировано kWh: {total_kwh}"
        ),
        "exchange.preview": ("🔁 Обмен: {kwh} kWh → {efhc} EFHC"),
        "ranks.me": "🏆 Ваш ранг: #{rank} · {total_kwh} kWh",
        "ranks.top.header": "Топ {limit}",
        "ranks.top.line": "#{rank} {username} — {total_kwh} kWh",
        "referrals.header": "👥 Рефералы",
        "referrals.active.count": "Активных: {count}",
        "referrals.inactive.count": "Неактивных: {count}",
        "tasks.submitted": "🎯 Задания",
        "admin.entry": "🛠 Откройте Admin Hub в WebApp ниже.",
        "admin.hub.entry": (
            "🧭 Управление Hub доступно через Admin Hub в WebApp."
        ),
        "faq.entry": (
            "❓ FAQ открыт в WebApp кнопкой ниже.\n"
            "Сейчас в FAQ: 20 разделов / 250 вопросов и ответов."
        ),
    },
    "uk": {
        "welcome": (
            "Вітаємо, {username}! ⚡\n"
            "VIP: {vip_flag}\n"
            "Панелі: {panels}\n"
            "Доступно kWh: {avail_kwh}"
        ),
        "menu": "Головне меню",
        "no_access": "⛔ Немає доступу.",
        "help": (
            "EFHC Bot — навігація до розділів WebApp.\n\n"
            "Основні команди:\n"
            "/start — відкрити головне меню\n"
            "/help — коротка довідка\n"
            "/hub — відкрити Hub\n"
            "/faq — відкрити FAQ\n"
            "/panels — зведення панелей\n"
            "/profile — профіль\n"
            "/balance — баланс\n"
            "/tasks — завдання\n"
            "/referrals — реферали\n"
            "/ranks — ранги\n"
            "/withdraw — виведення\n"
            "/webapp — відкрити Mini App\n\n"
            "FAQ: 20 розділів / 250 питань і відповідей.\n"
            "Hub — навігаційний шар проєкту."
        ),
        "subscribe.required": (
            "Для доступу потрібна підписка на канал {channel}."
        ),
        "panels.summary": (
            "⚡ Панелі\n"
            "Активно: {count}\n"
            "Генерація за сек.: {per_sec} kWh\n"
            "Доступно: {avail_kwh} kWh"
        ),
        "profile.header": "👤 Профіль",
        "profile.lines": (
            "tg_id: {tg_id}\n"
            "VIP: {vip_flag}\n"
            "Активних панелей: {panels}\n"
            "Доступно kWh: {avail_kwh}\n"
            "Усього згенеровано kWh: {total_kwh}"
        ),
        "exchange.preview": ("🔁 Обмін: {kwh} kWh → {efhc} EFHC"),
        "ranks.me": "🏆 Ваш ранг: #{rank} · {total_kwh} kWh",
        "ranks.top.header": "Топ {limit}",
        "ranks.top.line": "#{rank} {username} — {total_kwh} kWh",
        "referrals.header": "👥 Реферали",
        "referrals.active.count": "Активних: {count}",
        "referrals.inactive.count": "Неактивних: {count}",
        "tasks.submitted": "🎯 Завдання",
        "admin.entry": "🛠 Відкрийте Admin Hub у WebApp нижче.",
        "admin.hub.entry": (
            "🧭 Керування Hub доступне через Admin Hub у WebApp."
        ),
        "faq.entry": (
            "❓ FAQ відкрито у WebApp кнопкою нижче.\n"
            "Зараз у FAQ: 20 розділів / 250 питань і відповідей."
        ),
    },
    "de": {
        "welcome": (
            "Hallo, {username}! ⚡\n"
            "VIP: {vip_flag}\n"
            "Panels: {panels}\n"
            "Verfügbar kWh: {avail_kwh}"
        ),
        "menu": "Hauptmenü",
        "no_access": "⛔ Kein Zugriff.",
        "help": (
            "EFHC Bot ist die Navigation zu den WebApp-Bereichen.\n\n"
            "Hauptbefehle:\n"
            "/start — Hauptmenü öffnen\n"
            "/help — Kurzhilfe\n"
            "/hub — Hub öffnen\n"
            "/faq — FAQ öffnen\n"
            "/panels — Panels-Übersicht\n"
            "/profile — Profil\n"
            "/balance — Guthaben\n"
            "/tasks — Aufgaben\n"
            "/referrals — Empfehlungen\n"
            "/ranks — Ränge\n"
            "/withdraw — Auszahlung\n"
            "/webapp — Mini App öffnen\n\n"
            "FAQ: 20 Bereiche / 250 Fragen und Antworten.\n"
            "Hub ist die Navigationsschicht des Projekts."
        ),
        "subscribe.required": (
            "Abonnieren Sie {channel}, um fortzufahren."
        ),
        "panels.summary": (
            "⚡ Panels\n"
            "Aktiv: {count}\n"
            "Pro Sekunde: {per_sec} kWh\n"
            "Verfügbar: {avail_kwh} kWh"
        ),
        "profile.header": "👤 Profil",
        "profile.lines": (
            "tg_id: {tg_id}\n"
            "VIP: {vip_flag}\n"
            "Aktive Panels: {panels}\n"
            "Verfügbar kWh: {avail_kwh}\n"
            "Gesamt erzeugt kWh: {total_kwh}"
        ),
        "exchange.preview": ("🔁 Umtausch: {kwh} kWh → {efhc} EFHC"),
        "ranks.me": "🏆 Ihr Rang: #{rank} · {total_kwh} kWh",
        "ranks.top.header": "Top {limit}",
        "ranks.top.line": "#{rank} {username} — {total_kwh} kWh",
        "referrals.header": "👥 Empfehlungen",
        "referrals.active.count": "Aktiv: {count}",
        "referrals.inactive.count": "Inaktiv: {count}",
        "tasks.submitted": "🎯 Aufgaben",
        "admin.entry": "🛠 Admin Hub unten in WebApp öffnen.",
        "admin.hub.entry": (
            "🧭 Hub-Verwaltung ist über Admin Hub in WebApp verfügbar."
        ),
        "faq.entry": (
            "❓ FAQ über die Schaltfläche unten in WebApp öffnen.\n"
            "Aktueller FAQ-Stand: 20 Bereiche / 250 Q&A."
        ),
    },
    "fr": {
        "welcome": (
            "Bonjour, {username} ! ⚡\n"
            "VIP : {vip_flag}\n"
            "Panneaux : {panels}\n"
            "kWh disponibles : {avail_kwh}"
        ),
        "menu": "Menu principal",
        "no_access": "⛔ Accès refusé.",
        "help": (
            "EFHC Bot est la navigation vers les sections WebApp.\n\n"
            "Commandes principales :\n"
            "/start — ouvrir le menu principal\n"
            "/help — aide rapide\n"
            "/hub — ouvrir le Hub\n"
            "/faq — ouvrir la FAQ\n"
            "/panels — résumé des panneaux\n"
            "/profile — profil\n"
            "/balance — solde\n"
            "/tasks — tâches\n"
            "/referrals — parrainages\n"
            "/ranks — rangs\n"
            "/withdraw — retrait\n"
            "/webapp — ouvrir la Mini App\n\n"
            "FAQ : 20 sections / 250 questions et réponses.\n"
            "Le Hub est la couche de navigation du projet."
        ),
        "subscribe.required": (
            "Abonnez-vous à {channel} pour continuer."
        ),
        "panels.summary": (
            "⚡ Panneaux\n"
            "Actifs : {count}\n"
            "Par seconde : {per_sec} kWh\n"
            "Disponible : {avail_kwh} kWh"
        ),
        "profile.header": "👤 Profil",
        "profile.lines": (
            "tg_id : {tg_id}\n"
            "VIP : {vip_flag}\n"
            "Panneaux actifs : {panels}\n"
            "kWh disponibles : {avail_kwh}\n"
            "kWh générés au total : {total_kwh}"
        ),
        "exchange.preview": ("🔁 Échange : {kwh} kWh → {efhc} EFHC"),
        "ranks.me": "🏆 Votre rang : #{rank} · {total_kwh} kWh",
        "ranks.top.header": "Top {limit}",
        "ranks.top.line": "#{rank} {username} — {total_kwh} kWh",
        "referrals.header": "👥 Parrainages",
        "referrals.active.count": "Actifs : {count}",
        "referrals.inactive.count": "Inactifs : {count}",
        "tasks.submitted": "🎯 Tâches",
        "admin.entry": "🛠 Ouvrez Admin Hub dans WebApp ci-dessous.",
        "admin.hub.entry": (
            "🧭 La gestion du Hub est disponible via Admin Hub."
        ),
        "faq.entry": (
            "❓ Ouvrez la FAQ dans WebApp avec le bouton ci-dessous.\n"
            "FAQ actuelle : 20 sections / 250 Q&R."
        ),
    },
    "es": {
        "welcome": (
            "¡Hola, {username}! ⚡\n"
            "VIP: {vip_flag}\n"
            "Paneles: {panels}\n"
            "kWh disponibles: {avail_kwh}"
        ),
        "menu": "Menú principal",
        "no_access": "⛔ Acceso denegado.",
        "help": (
            "EFHC Bot es la navegación a las secciones WebApp.\n\n"
            "Comandos principales:\n"
            "/start — abrir el menú principal\n"
            "/help — ayuda rápida\n"
            "/hub — abrir Hub\n"
            "/faq — abrir FAQ\n"
            "/panels — resumen de paneles\n"
            "/profile — perfil\n"
            "/balance — saldo\n"
            "/tasks — tareas\n"
            "/referrals — referidos\n"
            "/ranks — rangos\n"
            "/withdraw — retiro\n"
            "/webapp — abrir Mini App\n\n"
            "FAQ: 20 secciones / 250 preguntas y respuestas.\n"
            "Hub es la capa de navegación del proyecto."
        ),
        "subscribe.required": (
            "Suscríbete a {channel} para continuar."
        ),
        "panels.summary": (
            "⚡ Paneles\n"
            "Activos: {count}\n"
            "Por segundo: {per_sec} kWh\n"
            "Disponible: {avail_kwh} kWh"
        ),
        "profile.header": "👤 Perfil",
        "profile.lines": (
            "tg_id: {tg_id}\n"
            "VIP: {vip_flag}\n"
            "Paneles activos: {panels}\n"
            "kWh disponibles: {avail_kwh}\n"
            "kWh generados en total: {total_kwh}"
        ),
        "exchange.preview": ("🔁 Cambio: {kwh} kWh → {efhc} EFHC"),
        "ranks.me": "🏆 Tu rango: #{rank} · {total_kwh} kWh",
        "ranks.top.header": "Top {limit}",
        "ranks.top.line": "#{rank} {username} — {total_kwh} kWh",
        "referrals.header": "👥 Referidos",
        "referrals.active.count": "Activos: {count}",
        "referrals.inactive.count": "Inactivos: {count}",
        "tasks.submitted": "🎯 Tareas",
        "admin.entry": "🛠 Abre Admin Hub en WebApp abajo.",
        "admin.hub.entry": (
            "🧭 La gestión de Hub está disponible en Admin Hub."
        ),
        "faq.entry": (
            "❓ Abre FAQ en WebApp con el botón de abajo.\n"
            "FAQ actual: 20 secciones / 250 preguntas y respuestas."
        ),
    },
    "it": {
        "welcome": (
            "Ciao, {username}! ⚡\n"
            "VIP: {vip_flag}\n"
            "Pannelli: {panels}\n"
            "kWh disponibili: {avail_kwh}"
        ),
        "menu": "Menu principale",
        "no_access": "⛔ Accesso negato.",
        "help": (
            "EFHC Bot è la navigazione verso le sezioni WebApp.\n\n"
            "Comandi principali:\n"
            "/start — aprire il menu principale\n"
            "/help — guida rapida\n"
            "/hub — aprire Hub\n"
            "/faq — aprire FAQ\n"
            "/panels — riepilogo pannelli\n"
            "/profile — profilo\n"
            "/balance — saldo\n"
            "/tasks — attività\n"
            "/referrals — referral\n"
            "/ranks — ranghi\n"
            "/withdraw — prelievo\n"
            "/webapp — aprire Mini App\n\n"
            "FAQ: 20 sezioni / 250 domande e risposte.\n"
            "Hub è il livello di navigazione del progetto."
        ),
        "subscribe.required": ("Iscriviti a {channel} per continuare."),
        "panels.summary": (
            "⚡ Pannelli\n"
            "Attivi: {count}\n"
            "Al secondo: {per_sec} kWh\n"
            "Disponibile: {avail_kwh} kWh"
        ),
        "profile.header": "👤 Profilo",
        "profile.lines": (
            "tg_id: {tg_id}\n"
            "VIP: {vip_flag}\n"
            "Pannelli attivi: {panels}\n"
            "kWh disponibili: {avail_kwh}\n"
            "kWh generati totali: {total_kwh}"
        ),
        "exchange.preview": ("🔁 Scambio: {kwh} kWh → {efhc} EFHC"),
        "ranks.me": "🏆 Il tuo rango: #{rank} · {total_kwh} kWh",
        "ranks.top.header": "Top {limit}",
        "ranks.top.line": "#{rank} {username} — {total_kwh} kWh",
        "referrals.header": "👥 Referral",
        "referrals.active.count": "Attivi: {count}",
        "referrals.inactive.count": "Inattivi: {count}",
        "tasks.submitted": "🎯 Attività",
        "admin.entry": "🛠 Apri Admin Hub in WebApp qui sotto.",
        "admin.hub.entry": (
            "🧭 La gestione Hub è disponibile tramite Admin Hub."
        ),
        "faq.entry": (
            "❓ Apri FAQ in WebApp con il pulsante qui sotto.\n"
            "FAQ attuale: 20 sezioni / 250 domande e risposte."
        ),
    },
    "pl": {
        "welcome": (
            "Cześć, {username}! ⚡\n"
            "VIP: {vip_flag}\n"
            "Panele: {panels}\n"
            "Dostępne kWh: {avail_kwh}"
        ),
        "menu": "Menu główne",
        "no_access": "⛔ Brak dostępu.",
        "help": (
            "EFHC Bot prowadzi do sekcji WebApp.\n\n"
            "Główne polecenia:\n"
            "/start — otworzyć menu główne\n"
            "/help — krótka pomoc\n"
            "/hub — otworzyć Hub\n"
            "/faq — otworzyć FAQ\n"
            "/panels — podsumowanie paneli\n"
            "/profile — profil\n"
            "/balance — saldo\n"
            "/tasks — zadania\n"
            "/referrals — polecenia\n"
            "/ranks — rangi\n"
            "/withdraw — wypłata\n"
            "/webapp — otworzyć Mini App\n\n"
            "FAQ: 20 sekcji / 250 pytań i odpowiedzi.\n"
            "Hub jest warstwą nawigacji projektu."
        ),
        "subscribe.required": (
            "Subskrybuj {channel}, aby kontynuować."
        ),
        "panels.summary": (
            "⚡ Panele\n"
            "Aktywne: {count}\n"
            "Na sekundę: {per_sec} kWh\n"
            "Dostępne: {avail_kwh} kWh"
        ),
        "profile.header": "👤 Profil",
        "profile.lines": (
            "tg_id: {tg_id}\n"
            "VIP: {vip_flag}\n"
            "Aktywne panele: {panels}\n"
            "Dostępne kWh: {avail_kwh}\n"
            "Łącznie wygenerowane kWh: {total_kwh}"
        ),
        "exchange.preview": ("🔁 Wymiana: {kwh} kWh → {efhc} EFHC"),
        "ranks.me": "🏆 Twój rang: #{rank} · {total_kwh} kWh",
        "ranks.top.header": "Top {limit}",
        "ranks.top.line": "#{rank} {username} — {total_kwh} kWh",
        "referrals.header": "👥 Polecenia",
        "referrals.active.count": "Aktywne: {count}",
        "referrals.inactive.count": "Nieaktywne: {count}",
        "tasks.submitted": "🎯 Zadania",
        "admin.entry": "🛠 Otwórz Admin Hub w WebApp poniżej.",
        "admin.hub.entry": (
            "🧭 Zarządzanie Hub jest dostępne przez Admin Hub."
        ),
        "faq.entry": (
            "❓ Otwórz FAQ w WebApp przyciskiem poniżej.\n"
            "Aktualne FAQ: 20 sekcji / 250 pytań i odpowiedzi."
        ),
    },
    "tr": {
        "welcome": (
            "Merhaba, {username}! ⚡\n"
            "VIP: {vip_flag}\n"
            "Paneller: {panels}\n"
            "Kullanılabilir kWh: {avail_kwh}"
        ),
        "menu": "Ana menü",
        "no_access": "⛔ Erişim yok.",
        "help": (
            "EFHC Bot, WebApp bölümlerine giden navigasyondur.\n\n"
            "Ana komutlar:\n"
            "/start — ana menüyü aç\n"
            "/help — kısa yardım\n"
            "/hub — Hub aç\n"
            "/faq — FAQ aç\n"
            "/panels — panel özeti\n"
            "/profile — profil\n"
            "/balance — bakiye\n"
            "/tasks — görevler\n"
            "/referrals — referanslar\n"
            "/ranks — rütbeler\n"
            "/withdraw — çekim\n"
            "/webapp — Mini App aç\n\n"
            "FAQ: 20 bölüm / 250 soru ve cevap.\n"
            "Hub, projenin navigasyon katmanıdır."
        ),
        "subscribe.required": (
            "Devam etmek için {channel} kanalına abone olun."
        ),
        "panels.summary": (
            "⚡ Paneller\n"
            "Aktif: {count}\n"
            "Saniye başına: {per_sec} kWh\n"
            "Kullanılabilir: {avail_kwh} kWh"
        ),
        "profile.header": "👤 Profil",
        "profile.lines": (
            "tg_id: {tg_id}\n"
            "VIP: {vip_flag}\n"
            "Aktif paneller: {panels}\n"
            "Kullanılabilir kWh: {avail_kwh}\n"
            "Toplam üretilen kWh: {total_kwh}"
        ),
        "exchange.preview": ("🔁 Değişim: {kwh} kWh → {efhc} EFHC"),
        "ranks.me": "🏆 Rütbeniz: #{rank} · {total_kwh} kWh",
        "ranks.top.header": "Top {limit}",
        "ranks.top.line": "#{rank} {username} — {total_kwh} kWh",
        "referrals.header": "👥 Referanslar",
        "referrals.active.count": "Aktif: {count}",
        "referrals.inactive.count": "Pasif: {count}",
        "tasks.submitted": "🎯 Görevler",
        "admin.entry": "🛠 Admin Hub'ı WebApp içinde aşağıdan açın.",
        "admin.hub.entry": (
            "🧭 Hub yönetimi Admin Hub üzerinden kullanılabilir."
        ),
        "faq.entry": (
            "❓ Aşağıdaki düğmeyle FAQ'yu WebApp içinde açın.\n"
            "Geçerli FAQ: 20 bölüm / 250 soru ve cevap."
        ),
    },
    "da": {
        "welcome": (
            "Hej, {username}! ⚡\n"
            "VIP: {vip_flag}\n"
            "Paneler: {panels}\n"
            "Tilgængelige kWh: {avail_kwh}"
        ),
        "menu": "Hovedmenu",
        "no_access": "⛔ Ingen adgang.",
        "help": (
            "EFHC Bot er navigationen til WebApp-sektionerne.\n\n"
            "Hovedkommandoer:\n"
            "/start — åbn hovedmenuen\n"
            "/help — kort hjælp\n"
            "/hub — åbn Hub\n"
            "/faq — åbn FAQ\n"
            "/panels — paneloversigt\n"
            "/profile — profil\n"
            "/balance — saldo\n"
            "/tasks — opgaver\n"
            "/referrals — henvisninger\n"
            "/ranks — rangeringer\n"
            "/withdraw — udbetaling\n"
            "/webapp — åbn Mini App\n\n"
            "FAQ: 20 sektioner / 250 spørgsmål og svar.\n"
            "Hub er projektets navigationslag."
        ),
        "subscribe.required": (
            "Abonner på {channel} for at fortsætte."
        ),
        "panels.summary": (
            "⚡ Paneler\n"
            "Aktive: {count}\n"
            "Pr. sekund: {per_sec} kWh\n"
            "Tilgængelige: {avail_kwh} kWh"
        ),
        "profile.header": "👤 Profil",
        "profile.lines": (
            "tg_id: {tg_id}\n"
            "VIP: {vip_flag}\n"
            "Aktive paneler: {panels}\n"
            "Tilgængelige kWh: {avail_kwh}\n"
            "Samlet genereret kWh: {total_kwh}"
        ),
        "exchange.preview": ("🔁 Veksling: {kwh} kWh → {efhc} EFHC"),
        "ranks.me": "🏆 Din rang: #{rank} · {total_kwh} kWh",
        "ranks.top.header": "Top {limit}",
        "ranks.top.line": "#{rank} {username} — {total_kwh} kWh",
        "referrals.header": "👥 Henvisninger",
        "referrals.active.count": "Aktive: {count}",
        "referrals.inactive.count": "Inaktive: {count}",
        "tasks.submitted": "🎯 Opgaver",
        "admin.entry": "🛠 Åbn Admin Hub i WebApp nedenfor.",
        "admin.hub.entry": (
            "🧭 Hub-styring er tilgængelig via Admin Hub."
        ),
        "faq.entry": (
            "❓ Åbn FAQ i WebApp med knappen nedenfor.\n"
            "Aktuel FAQ: 20 sektioner / 250 spørgsmål og svar."
        ),
    },
    "hi": {
        "welcome": (
            "नमस्ते, {username}! ⚡\n"
            "VIP: {vip_flag}\n"
            "पैनल: {panels}\n"
            "उपलब्ध kWh: {avail_kwh}"
        ),
        "menu": "मुख्य मेनू",
        "no_access": "⛔ प्रवेश उपलब्ध नहीं है.",
        "help": (
            "EFHC Bot WebApp अनुभागों की नेविगेशन परत है.\n\n"
            "मुख्य कमांड:\n"
            "/start — मुख्य मेनू खोलें\n"
            "/help — संक्षिप्त सहायता\n"
            "/hub — Hub खोलें\n"
            "/faq — FAQ खोलें\n"
            "/panels — पैनल सारांश\n"
            "/profile — प्रोफ़ाइल\n"
            "/balance — बैलेंस\n"
            "/tasks — कार्य\n"
            "/referrals — रेफ़रल\n"
            "/ranks — रैंक\n"
            "/withdraw — निकासी\n"
            "/webapp — Mini App खोलें\n\n"
            "FAQ: 20 अनुभाग / 250 प्रश्न और उत्तर.\n"
            "Hub परियोजना की नेविगेशन परत है."
        ),
        "subscribe.required": (
            "जारी रखने के लिए {channel} की सदस्यता लें."
        ),
        "panels.summary": (
            "⚡ पैनल\n"
            "सक्रिय: {count}\n"
            "प्रति सेकंड: {per_sec} kWh\n"
            "उपलब्ध: {avail_kwh} kWh"
        ),
        "profile.header": "👤 प्रोफ़ाइल",
        "profile.lines": (
            "tg_id: {tg_id}\n"
            "VIP: {vip_flag}\n"
            "सक्रिय पैनल: {panels}\n"
            "उपलब्ध kWh: {avail_kwh}\n"
            "कुल उत्पन्न kWh: {total_kwh}"
        ),
        "exchange.preview": ("🔁 विनिमय: {kwh} kWh → {efhc} EFHC"),
        "ranks.me": "🏆 आपकी रैंक: #{rank} · {total_kwh} kWh",
        "ranks.top.header": "शीर्ष {limit}",
        "ranks.top.line": "#{rank} {username} — {total_kwh} kWh",
        "referrals.header": "👥 रेफ़रल",
        "referrals.active.count": "सक्रिय: {count}",
        "referrals.inactive.count": "निष्क्रिय: {count}",
        "tasks.submitted": "🎯 कार्य",
        "admin.entry": "🛠 नीचे WebApp में Admin Hub खोलें.",
        "admin.hub.entry": (
            "🧭 Hub प्रबंधन Admin Hub के माध्यम से उपलब्ध है."
        ),
        "faq.entry": (
            "❓ नीचे दिए गए बटन से WebApp में FAQ खोलें.\n"
            "वर्तमान FAQ: 20 अनुभाग / 250 प्रश्न और उत्तर."
        ),
    },
    "id": {
        "welcome": (
            "Halo, {username}! ⚡\n"
            "VIP: {vip_flag}\n"
            "Panel: {panels}\n"
            "kWh tersedia: {avail_kwh}"
        ),
        "menu": "Menu utama",
        "no_access": "⛔ Akses ditolak.",
        "help": (
            "EFHC Bot adalah navigasi ke bagian WebApp.\n\n"
            "Perintah utama:\n"
            "/start — buka menu utama\n"
            "/help — bantuan singkat\n"
            "/hub — buka Hub\n"
            "/faq — buka FAQ\n"
            "/panels — ringkasan panel\n"
            "/profile — profil\n"
            "/balance — saldo\n"
            "/tasks — tugas\n"
            "/referrals — referral\n"
            "/ranks — peringkat\n"
            "/withdraw — penarikan\n"
            "/webapp — buka Mini App\n\n"
            "FAQ: 20 bagian / 250 pertanyaan dan jawaban.\n"
            "Hub adalah lapisan navigasi proyek."
        ),
        "subscribe.required": (
            "Berlangganan {channel} untuk melanjutkan."
        ),
        "panels.summary": (
            "⚡ Panel\n"
            "Aktif: {count}\n"
            "Per detik: {per_sec} kWh\n"
            "Tersedia: {avail_kwh} kWh"
        ),
        "profile.header": "👤 Profil",
        "profile.lines": (
            "tg_id: {tg_id}\n"
            "VIP: {vip_flag}\n"
            "Panel aktif: {panels}\n"
            "kWh tersedia: {avail_kwh}\n"
            "Total kWh dihasilkan: {total_kwh}"
        ),
        "exchange.preview": ("🔁 Tukar: {kwh} kWh → {efhc} EFHC"),
        "ranks.me": "🏆 Peringkat Anda: #{rank} · {total_kwh} kWh",
        "ranks.top.header": "Top {limit}",
        "ranks.top.line": "#{rank} {username} — {total_kwh} kWh",
        "referrals.header": "👥 Referral",
        "referrals.active.count": "Aktif: {count}",
        "referrals.inactive.count": "Tidak aktif: {count}",
        "tasks.submitted": "🎯 Tugas",
        "admin.entry": "🛠 Buka Admin Hub di WebApp di bawah.",
        "admin.hub.entry": (
            "🧭 Manajemen Hub tersedia melalui Admin Hub."
        ),
        "faq.entry": (
            "❓ Buka FAQ di WebApp dengan tombol di bawah.\n"
            "FAQ saat ini: 20 bagian / 250 pertanyaan dan jawaban."
        ),
    },
    "sw": {
        "welcome": (
            "Habari, {username}! ⚡\n"
            "VIP: {vip_flag}\n"
            "Paneli: {panels}\n"
            "kWh inayopatikana: {avail_kwh}"
        ),
        "menu": "Menyu kuu",
        "no_access": "⛔ Hakuna ufikiaji.",
        "help": (
            "EFHC Bot ni urambazaji wa sehemu za WebApp.\n\n"
            "Amri kuu:\n"
            "/start — fungua menyu kuu\n"
            "/help — msaada mfupi\n"
            "/hub — fungua Hub\n"
            "/faq — fungua FAQ\n"
            "/panels — muhtasari wa paneli\n"
            "/profile — wasifu\n"
            "/balance — salio\n"
            "/tasks — kazi\n"
            "/referrals — marejeleo\n"
            "/ranks — viwango\n"
            "/withdraw — kutoa\n"
            "/webapp — fungua Mini App\n\n"
            "FAQ: sehemu 20 / maswali na majibu 250.\n"
            "Hub ni tabaka la urambazaji wa mradi."
        ),
        "subscribe.required": (
            "Jisajili kwenye {channel} ili kuendelea."
        ),
        "panels.summary": (
            "⚡ Paneli\n"
            "Hai: {count}\n"
            "Kwa sekunde: {per_sec} kWh\n"
            "Inapatikana: {avail_kwh} kWh"
        ),
        "profile.header": "👤 Wasifu",
        "profile.lines": (
            "tg_id: {tg_id}\n"
            "VIP: {vip_flag}\n"
            "Paneli hai: {panels}\n"
            "kWh inayopatikana: {avail_kwh}\n"
            "Jumla ya kWh iliyozalishwa: {total_kwh}"
        ),
        "exchange.preview": ("🔁 Badilisha: {kwh} kWh → {efhc} EFHC"),
        "ranks.me": "🏆 Kiwango chako: #{rank} · {total_kwh} kWh",
        "ranks.top.header": "Juu {limit}",
        "ranks.top.line": "#{rank} {username} — {total_kwh} kWh",
        "referrals.header": "👥 Marejeleo",
        "referrals.active.count": "Hai: {count}",
        "referrals.inactive.count": "Si hai: {count}",
        "tasks.submitted": "🎯 Kazi",
        "admin.entry": "🛠 Fungua Admin Hub katika WebApp hapa chini.",
        "admin.hub.entry": (
            "🧭 Usimamizi wa Hub unapatikana kupitia Admin Hub."
        ),
        "faq.entry": (
            "❓ Fungua FAQ katika WebApp kwa kitufe kilicho chini.\n"
            "FAQ ya sasa: sehemu 20 / maswali na majibu 250."
        ),
    },
    "pt": {
        "welcome": (
            "Olá, {username}! ⚡\n"
            "VIP: {vip_flag}\n"
            "Painéis: {panels}\n"
            "kWh disponíveis: {avail_kwh}"
        ),
        "menu": "Menu principal",
        "no_access": "⛔ Sem acesso.",
        "help": (
            "EFHC Bot — navegação para as secções do WebApp.\n\n"
            "Comandos principais:\n"
            "/start — abrir menu principal\n"
            "/help — ajuda rápida\n"
            "/hub — abrir Hub\n"
            "/faq — abrir FAQ\n"
            "/panels — resumo dos painéis\n"
            "/profile — perfil\n"
            "/balance — saldo\n"
            "/tasks — tarefas\n"
            "/referrals — referidos\n"
            "/ranks — classificações\n"
            "/withdraw — levantamento\n"
            "/webapp — abrir Mini App\n\n"
            "FAQ: 20 secções / 250 perguntas e respostas.\n"
            "O Hub é a camada de navegação do projeto."
        ),
        "subscribe.required": (
            "Para aceder, é necessária uma subscrição do canal {channel}."
        ),
        "panels.summary": (
            "⚡ Painéis\n"
            "Ativos: {count}\n"
            "Geração por segundo: {per_sec} kWh\n"
            "Disponível: {avail_kwh} kWh"
        ),
        "profile.header": "👤 Perfil",
        "profile.lines": (
            "tg_id: {tg_id}\n"
            "VIP: {vip_flag}\n"
            "Painéis ativos: {panels}\n"
            "kWh disponíveis: {avail_kwh}\n"
            "Total de kWh gerados: {total_kwh}"
        ),
        "exchange.preview": "🔁 Troca: {kwh} kWh → {efhc} EFHC",
        "ranks.me": "🏆 A sua posição: #{rank} · {total_kwh} kWh",
        "ranks.top.header": "Top {limit}",
        "ranks.top.line": "#{rank} {username} — {total_kwh} kWh",
        "referrals.header": "👥 Referidos",
        "referrals.active.count": "Ativos: {count}",
        "referrals.inactive.count": "Inativos: {count}",
        "tasks.submitted": "🎯 Tarefas",
        "admin.entry": "🛠 Abra o Admin Hub no WebApp abaixo.",
        "admin.hub.entry": (
            "🧭 A gestão do Hub está disponível através do Admin Hub."
        ),
        "faq.entry": (
            "❓ Abra o FAQ no WebApp com o botão abaixo.\n"
            "FAQ atual: 20 secções / 250 perguntas e respostas."
        ),
    },
    "ko": {
        "welcome": (
            "안녕하세요, {username}! ⚡\n"
            "VIP: {vip_flag}\n"
            "패널: {panels}\n"
            "사용 가능한 kWh: {avail_kwh}"
        ),
        "menu": "메인 메뉴",
        "no_access": "⛔ 접근 권한이 없습니다.",
        "help": (
            "EFHC Bot — WebApp 섹션 내비게이션입니다.\n\n"
            "주요 명령어:\n"
            "/start — 메인 메뉴 열기\n"
            "/help — 빠른 도움말\n"
            "/hub — Hub 열기\n"
            "/faq — FAQ 열기\n"
            "/panels — 패널 요약\n"
            "/profile — 프로필\n"
            "/balance — 잔액\n"
            "/tasks — 작업\n"
            "/referrals — 추천\n"
            "/ranks — 랭크\n"
            "/withdraw — 출금\n"
            "/webapp — Mini App 열기\n\n"
            "FAQ: 20개 섹션 / 질문과 답변 250개.\n"
            "Hub는 프로젝트의 내비게이션 계층입니다."
        ),
        "subscribe.required": (
            "접근하려면 {channel} 채널 구독이 필요합니다."
        ),
        "panels.summary": (
            "⚡ 패널\n"
            "활성: {count}\n"
            "초당 발전량: {per_sec} kWh\n"
            "사용 가능: {avail_kwh} kWh"
        ),
        "profile.header": "👤 프로필",
        "profile.lines": (
            "tg_id: {tg_id}\n"
            "VIP: {vip_flag}\n"
            "활성 패널: {panels}\n"
            "사용 가능한 kWh: {avail_kwh}\n"
            "총 생성 kWh: {total_kwh}"
        ),
        "exchange.preview": "🔁 교환: {kwh} kWh → {efhc} EFHC",
        "ranks.me": "🏆 내 위치: #{rank} · {total_kwh} kWh",
        "ranks.top.header": "상위 {limit}",
        "ranks.top.line": "#{rank} {username} — {total_kwh} kWh",
        "referrals.header": "👥 추천",
        "referrals.active.count": "활성: {count}",
        "referrals.inactive.count": "비활성: {count}",
        "tasks.submitted": "🎯 작업",
        "admin.entry": "🛠 아래 WebApp에서 Admin Hub를 여세요.",
        "admin.hub.entry": (
            "🧭 Hub 관리는 Admin Hub에서 이용할 수 있습니다."
        ),
        "faq.entry": (
            "❓ 아래 버튼으로 WebApp의 FAQ를 여세요.\n"
            "현재 FAQ: 20개 섹션 / 질문과 답변 250개."
        ),
    },
    "ja": {
        "welcome": (
            "こんにちは、{username}さん！ ⚡\n"
            "VIP: {vip_flag}\n"
            "パネル: {panels}\n"
            "利用可能なkWh: {avail_kwh}"
        ),
        "menu": "メインメニュー",
        "no_access": "⛔ アクセス権がありません。",
        "help": (
            "EFHC Bot — WebAppセクションのナビゲーションです。\n\n"
            "主なコマンド:\n"
            "/start — メインメニューを開く\n"
            "/help — クイックヘルプ\n"
            "/hub — Hubを開く\n"
            "/faq — FAQを開く\n"
            "/panels — パネル概要\n"
            "/profile — プロフィール\n"
            "/balance — 残高\n"
            "/tasks — タスク\n"
            "/referrals — 紹介\n"
            "/ranks — Ranks\n"
            "/withdraw — 出金\n"
            "/webapp — Mini Appを開く\n\n"
            "FAQ: 20セクション / 250件の質問と回答。\n"
            "Hubはプロジェクトのナビゲーション層です。"
        ),
        "subscribe.required": (
            "アクセスするには、チャンネル{channel}への登録が必要です。"
        ),
        "panels.summary": (
            "⚡ パネル\n"
            "有効: {count}\n"
            "毎秒の発電量: {per_sec} kWh\n"
            "利用可能: {avail_kwh} kWh"
        ),
        "profile.header": "👤 プロフィール",
        "profile.lines": (
            "tg_id: {tg_id}\n"
            "VIP: {vip_flag}\n"
            "有効なパネル: {panels}\n"
            "利用可能なkWh: {avail_kwh}\n"
            "総生成kWh: {total_kwh}"
        ),
        "exchange.preview": "🔁 交換: {kwh} kWh → {efhc} EFHC",
        "ranks.me": "🏆 現在の順位: #{rank} · {total_kwh} kWh",
        "ranks.top.header": "トップ{limit}",
        "ranks.top.line": "#{rank} {username} — {total_kwh} kWh",
        "referrals.header": "👥 紹介",
        "referrals.active.count": "有効: {count}",
        "referrals.inactive.count": "無効: {count}",
        "tasks.submitted": "🎯 タスク",
        "admin.entry": "🛠 下のWebAppからAdmin Hubを開いてください。",
        "admin.hub.entry": (
            "🧭 Hubの管理はAdmin Hubから利用できます。"
        ),
        "faq.entry": (
            "❓ 下のボタンからWebAppのFAQを開いてください。\n"
            "現在のFAQ: 20セクション / 250件の質問と回答。"
        ),
    },
}


_PLACEHOLDER_FORMATTER = string.Formatter()


def _placeholders(value: str) -> set[str]:
    names: set[str] = set()
    for _, field_name, _, _ in _PLACEHOLDER_FORMATTER.parse(value):
        if field_name:
            names.add(field_name.split(".", 1)[0].split("[", 1)[0])
    return names


def validate_bot_texts() -> None:
    """Validate key parity and placeholder parity for bot texts."""
    baseline = set(BOT_TEXT_KEYS)
    en_placeholders = {
        key: _placeholders(TEXTS["en"][key]) for key in BOT_TEXT_KEYS
    }
    for lang in BOT_TEXT_LANGS:
        values = TEXTS.get(lang)
        if values is None:
            raise RuntimeError(f"missing language: {lang}")
        keys = set(values)
        if keys != baseline:
            raise RuntimeError(f"bot text key drift: {lang}")
        for key in BOT_TEXT_KEYS:
            if not values[key].strip():
                raise RuntimeError(f"empty bot text: {lang}.{key}")
            got = _placeholders(values[key])
            if got != en_placeholders[key]:
                raise RuntimeError(
                    "bot text placeholder drift: "
                    f"{lang}.{key}: {sorted(got)}"
                )


def t(*args: str, **fmt: Any) -> str:
    """Return localized bot text.

    Supports backward-compatible call styles.
    """
    if not args:
        raise TypeError("t() requires at least one positional argument")
    if len(args) == 1:
        lang = "ru"
        key = args[0]
    else:
        maybe_lang, maybe_key = args[0], args[1]
        if maybe_lang in TEXTS:
            lang = maybe_lang
            key = maybe_key
        else:
            lang = "ru"
            key = maybe_lang
    d = TEXTS.get(lang) or TEXTS["ru"]
    template = d.get(key) or TEXTS["ru"].get(key)
    if template is None:
        template = TEXTS["en"].get(key) or key
    return template.format(**fmt)


validate_bot_texts()
