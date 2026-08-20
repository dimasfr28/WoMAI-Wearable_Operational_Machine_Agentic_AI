import re

with open('backend/app/api/routes_sensor.py', 'r', encoding='utf-8') as f:
    content = f.read()

simulation_manager_code = """
import asyncio
from datetime import datetime, timedelta
import random

class SimulationManager:
    _tasks = {}
    _state = {}

    @classmethod
    def start_simulation(cls, machine_id: str):
        if machine_id in cls._tasks and not cls._tasks[machine_id].done():
            return
        cls._state[machine_id] = {"tool_wear": 0.0}
        cls._tasks[machine_id] = asyncio.create_task(cls._run_simulation(machine_id))

    @classmethod
    def restart_simulation(cls, machine_id: str):
        if machine_id in cls._tasks:
            cls._tasks[machine_id].cancel()
        cls._state[machine_id] = {"tool_wear": 0.0}
        cls._tasks[machine_id] = asyncio.create_task(cls._run_simulation(machine_id))

    @classmethod
    async def _run_simulation(cls, machine_id: str):
        from app.db.session import SessionLocal
        from app.db.models import SensorReading, Machine
        from app.ml.predictor_clasification import predict_failure
        from app.schemas.sensor import SensorReadingIn
        try:
            while True:
                await asyncio.sleep(300) # Wait 5 minutes
                db = SessionLocal()
                try:
                    machine = db.query(Machine).filter(Machine.id == machine_id).first()
                    if not machine:
                        break

                    now = datetime.now()
                    readings = []
                    
                    # Generate 60 rows representing 5 mins (1 per 5 secs)
                    for i in range(60):
                        current_time = now - timedelta(seconds=5 * (59 - i))
                        air_temp = round(random.uniform(298.0, 300.0), 1)
                        proc_temp = round(air_temp + random.uniform(10.0, 11.0), 1)
                        rpm = random.randint(1300, 2000)
                        
                        cls._state[machine_id]["tool_wear"] += (5.0 / 60.0)
                        
                        item = SensorReadingIn(
                            timestamp=current_time,
                            air_temperature_k=air_temp,
                            process_temperature_k=proc_temp,
                            rotational_speed_rpm=rpm,
                            tool_wear_min=round(cls._state[machine_id]["tool_wear"], 2)
                        )
                        readings.append(item)
                    
                    for idx, item in enumerate(readings):
                        run = assign_run_id(item, db, machine_id)
                        reading = SensorReading(
                            run_id=run.id,
                            reading_timestamp=item.timestamp,
                            air_temperature_k=item.air_temperature_k,
                            process_temperature_k=item.process_temperature_k,
                            rotational_speed_rpm=item.rotational_speed_rpm,
                            tool_wear_min=item.tool_wear_min,
                            machine_failure=None,
                            input_source="simulation",
                        )
                        db.add(reading)
                        db.commit()
                        db.refresh(reading)
                        
                        feature_row = {
                            "air_temperature_k": float(reading.air_temperature_k),
                            "process_temperature_k": float(reading.process_temperature_k),
                            "rotational_speed_rpm": reading.rotational_speed_rpm,
                            "tool_wear_min": float(reading.tool_wear_min),
                        }
                        pred_result = predict_failure(feature_row)
                        reading.machine_failure = pred_result.label
                        db.commit()
                        db.refresh(reading)
                        
                        _bump_failure_count_if_needed(db, run, pred_result.label)
                        
                        if idx == 59:
                            report = None
                            try:
                                report = _run_report_pipeline(db, reading, pred_result, machine_id)
                            except Exception as e:
                                logger.error(f"Simulation pipeline error: {e}")
                            
                            notify_new_reading(
                                machine.name,
                                pred_result,
                                horizon_probability=report.horizon_prediction.failure_probability if report and report.horizon_prediction else None,
                                horizon_minutes=report.horizon_prediction.horizon_minutes if report and report.horizon_prediction else None,
                                run_label=run.run_label,
                                health_score=report.prediction.health_score if report else None,
                                top_feature_name=report.shap.features[0].feature_name if report and report.shap.features else None,
                                cause_analysis_short=report.cause_analysis_short if report else None,
                            )
                except Exception as e:
                    logger.error(f"Error in simulation task: {e}")
                finally:
                    db.close()
        except asyncio.CancelledError:
            pass

"""

# Insert SimulationManager above submit_reading
pattern_submit = r'(@router\.post\("/readings", response_model=SensorReadingSubmitResponseOut\)\ndef submit_reading\()'
content = re.sub(pattern_submit, simulation_manager_code + r'\n\n\1', content, count=1)

# Modify submit_reading to call start_simulation
pattern_start = r'(def submit_reading\([\s\S]*?machine = _require_machine\(db, machine_id\))'
content = re.sub(pattern_start, r'\1\n    SimulationManager.start_simulation(machine_id)', content, count=1)

# Add /machine-diagnosis endpoint
machine_diagnosis_code = """
@router.post("/machine-diagnosis")
def machine_diagnosis(machine_id: str):
    SimulationManager.restart_simulation(machine_id)
    return {"message": f"Simulation restarted for machine {machine_id}"}
"""

content += "\n" + machine_diagnosis_code

with open('backend/app/api/routes_sensor.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Patch applied.")
