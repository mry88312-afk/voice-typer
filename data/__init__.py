"""data — 健壯持久化層。config/env/profiles 走 JsonStore (原子+備份+重試)；usage/history/learned 為 append-only 日誌。"""
