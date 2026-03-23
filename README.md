# Cyberpunk Soccer Game

## MVP Version (V1.0) Completed

This project has reached the Minimum Viable Product (MVP) stage and is currently closed in this version.

## Project Status

- Status: MVP stage completed
- Version: V1.0

## MVP Scope

### Online Gameplay (2 players)

- 1v1 matchmaking via WebSocket
- Turn system: shooter / goalkeeper
- Round outcome: GOAL or SAVED
- Role swap after each round
- Cyberpunk-style messages and animations
- Rematch panel after game over

### Rules and Match-End System

- Player lives based on score
- Field elimination (offline nodes) during a match
- Game ends at 0 lives or when the board is exhausted
- Draw when draw conditions are met

### Account and Profile

- Registration and login (nickname + password)
- Password hashing (PBKDF2 + salt)
- Player profile view
- Profile statistics
- Match history

### Database

- MongoDB (motor)
- Match history persistence
- Profile statistics aggregation
- Database health check endpoint

## Tech Stack

- Backend: FastAPI
- Frontend: HTML + CSS + JavaScript
- Realtime communication: WebSocket
- Database: MongoDB (motor)

## Local Run

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Configure the `MONGODB_URL` environment variable in the `.env` file.
4. Run the app:

```bash
uvicorn main:app --reload
```

5. Open the app in your browser at `http://127.0.0.1:8000`.

## Final Note

This version represents a complete MVP (V1.0) and is ready for core product demonstration.
