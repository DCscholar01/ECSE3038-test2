from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
import secrets
import os
from pymongo import MongoClient
from dotenv import load_dotenv
load_dotenv()

app = FastAPI()

# Connect to MongoDB Atlas (reads from your .env file or environment)
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
client = MongoClient(MONGODB_URI)
db = client.db_ecse3038_test2
fans_collection = db.fans

class FanCreate(BaseModel):
    mac: str
    room: str

@app.post("/fans", status_code=status.HTTP_201_CREATED)
def create_fan(fan: FanCreate):
    # Check if a fan with this MAC already exists
    existing = fans_collection.find_one({"mac": fan.mac})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, 
            detail="Fan with this MAC address already exists."
        )
    
    # Generate a random API key
    api_key = secrets.token_urlsafe(16)
    
    fan_doc = {
        "mac": fan.mac,
        "room": fan.room,
        "key": api_key
    }
    
    fans_collection.insert_one(fan_doc)
    
    # Return the details including the key so the device can capture it once
    return {
        "mac": fan.mac,
        "room": fan.room,
        "key": api_key
    }

@app.get("/fans")
def get_fans():
    # Retrieve all fans, explicitly excluding the 'key' and MongoDB '_id' fields
    fans = list(fans_collection.find({}, {"_id": 0, "key": 0}))
    return fans

@app.get("/fans/{mac}")
def get_fan(mac: str):
    # Find a specific fan, excluding the 'key' and '_id' fields
    fan = fans_collection.find_one({"mac": mac}, {"_id": 0, "key": 0})
    if not fan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Fan not found."
        )
    return fan
