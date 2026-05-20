import logging
import json
import re
from datetime import datetime
from bot.db import (
    create_mission as db_create_mission,
    get_mission as db_get_mission,
    list_missions as db_list_missions,
    update_mission_status as db_update_mission_status,
    confirm_mission_step as db_confirm_mission_step,
    update_mission_step as db_update_mission_step,
    save_mission_report as db_save_mission_report,
)

logger = logging.getLogger(__name__)

MISSION_PREFIXES = (
    "nova missao ", "nova missão ", "iniciar missao ", "iniciar missão ",
    "criar missao ", "criar missão ", "objetivo: ", "missao: ", "missão: ",
)

def _extract_mission_goal(text):
    stripped = text.strip()
    lowered = stripped.lower()
    for prefix in MISSION_PREFIXES:
        if lowered.startswith(prefix):
            return stripped[len(prefix):].strip()
    return None

def format_mission_details(mission):
    if not mission:
        return "Missao nao encontrada."
    
    lines = [
        f"🎯 Missao #{mission['id']}: {mission['goal']}",
        f"Status: {mission['status'].upper()}",
        f"Passo atual: {mission['current_step']}",
        "\nPlano:"
    ]
    
    for step in mission.get("steps", []):
        marker = "✅" if step["status"] == "done" else "⏳"
        if step["status"] == "blocked": marker = "🚫"
        if step["status"] == "skipped": marker = "⏭️"
        
        line = f"{step['step_number']}. {marker} {step['title']}"
        if step.get("requires_confirmation") and not step.get("confirmed_at"):
            line += " (⚠️ Requer confirmacao)"
        lines.append(line)
        
    if mission.get("last_report"):
        lines.append(f"\n📝 Ultimo Relatorio:\n{mission['last_report'][:200]}...")
        
    return "\n".join(lines)

def handle_create_mission(user_id, text):
    goal = _extract_mission_goal(text)
    if not goal:
        return None, "Por favor, descreva o objetivo da missao."
    
    # Placeholder for AI step generation logic if needed
    # For now, just create with initial objective
    mission_id = db_create_mission(user_id, goal, steps=None)
    return mission_id, None
