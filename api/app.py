from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
import secrets
import os
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime, timezone
from fastapi import Header
from fastapi import Query
import json
import os
import paho.mqtt.client as mqtt
from fastapi.responses import JSONResponse
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

#A2

class ReadingCreate(BaseModel):
    mac: str
    humidity: float

@app.post("/readings", status_code=status.HTTP_201_CREATED)
def create_reading(reading: ReadingCreate, x_api_key: str = Header(None)):
    # 1. Check if X-API-Key header is missing or empty
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header."
        )
    
    # 2. Find the fan corresponding to the provided MAC address
    fan = fans_collection.find_one({"mac": reading.mac})
    
    # If the MAC itself doesn't exist, check if the key belongs to ANY other fan or is completely invalid
    if not fan:
        # Check if the key exists anywhere in the database to distinguish between 401 and 403
        key_exists = fans_collection.find_one({"key": x_api_key})
        if not key_exists:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key."
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API key belongs to another MAC."
            )
            
    # 3. Check if the key matches this specific fan
    if fan.get("key") != x_api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key belongs to another MAC."
        )
        
    # 4. Validate humidity range (0 to 100)
    if not (0 <= reading.humidity <= 100):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Humidity must be between 0 and 100."
        )
        
    # 5. Save the reading with a server-generated timestamp
    reading_doc = {
        "mac": reading.mac,
        "humidity": reading.humidity,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    db.readings.insert_one(reading_doc)
    
    return {"message": "Reading recorded successfully"}

#A3

    

@app.get("/readings")
def get_readings(
    mac: str | None = None,
    limit: int = Query(10, ge=1, le=100)
):
    # Build query filter if mac is provided
    query = {}
    if mac:
        query["mac"] = mac
        
    # Retrieve readings from MongoDB: sorted by _id descending (newest first), limited, and excluding MongoDB's _id field
    readings = list(
        db.readings.find(query, {"_id": 0})
        .sort("_id", -1)
        .limit(limit)
    )

    return readings

#A4

BROKER_HOST = "135.232.203.144"
BROKER_PORT = 1883
MQTT_NAME = os.getenv("MQTT_NAME", "my_name")

class SettingsUpdate(BaseModel):
    mode: str
    max_humidity: float

@app.put("/fans/{mac}/settings")
def update_fan_settings(mac: str, settings: SettingsUpdate):
    # 1. Check if the fan exists
    fan = fans_collection.find_one({"mac": mac})
    if not fan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fan not found."
        )
        
    # 2. Validate mode value (must be exactly auto, on, or off)
    if settings.mode not in ["auto", "on", "off"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Mode must be exactly 'auto', 'on', or 'off'."
        )
        
    # 3. Validate max_humidity range (0 to 100)
    if not (0 <= settings.max_humidity <= 100):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="max_humidity must be between 0 and 100."
        )
        
    # 4. Check if settings already exist for this MAC to determine status code (201 vs 200)
    existing_setting = db.settings.find_one({"mac": mac})
    response_status = status.HTTP_200_OK
    
    setting_doc = {
        "mac": mac,
        "mode": settings.mode,
        "max_humidity": settings.max_humidity
    }
    
    if not existing_setting:
        response_status = status.HTTP_201_CREATED
        db.settings.insert_one(setting_doc)
    else:
        db.settings.update_one({"mac": mac}, {"$set": setting_doc})
        
    # 5. Publish retained MQTT message
    topic = f"ecse3038/{MQTT_NAME}/fan/settings"
    payload = json.dumps({
        "mode": settings.mode,
        "max_humidity": settings.max_humidity
    })
    
    try:
        mqtt_client = mqtt.Client()
        mqtt_client.connect(BROKER_HOST, BROKER_PORT, 60)
        mqtt_client.publish(topic, payload, retain=True)
        mqtt_client.disconnect()
    except Exception as e:
        print(f"Failed to publish MQTT message: {e}")
        
    return JSONResponse(
        status_code=response_status,
        content={"mode": settings.mode, "max_humidity": settings.max_humidity}
    )

#A5

@app.delete("/fans/{mac}", status_code=status.HTTP_204_NO_CONTENT)
def delete_fan(mac: str, x_api_key: str = Header(None)):
    # 1. Check if the fan exists
    fan = fans_collection.find_one({"mac": mac})
    if not fan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fan not found."
        )
        
    # 2. Check if X-API-Key header is missing or if the key is completely unknown
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header."
        )
        
    # Check if this key exists anywhere in the database to differentiate between 401 and 403
    key_exists = fans_collection.find_one({"key": x_api_key})
    if not key_exists:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key."
        )
        
    # 3. Check if the provided key belongs to another fan (403 Forbidden)
    if fan.get("key") != x_api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key belongs to another MAC."
        )
        
    # 4. Delete the fan from MongoDB
    fans_collection.delete_one({"mac": mac})
    
    # Also clean up any associated settings or readings if desired (optional)
    db.settings.delete_many({"mac": mac})
    
    return None

#all of B

