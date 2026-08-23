import argparse,time
from app.core.config import settings
from app.services.calendar_worker import run_once
def main():
 parser=argparse.ArgumentParser();parser.add_argument("--once",action="store_true");parser.add_argument("--poll-seconds",type=int,default=settings.notification_poll_seconds);args=parser.parse_args()
 try:
  while True:
   counts=run_once();print(" ".join(f"{key}={value}" for key,value in counts.items()),flush=True)
   if args.once:return
   time.sleep(max(1,args.poll_seconds))
 except KeyboardInterrupt:return
if __name__ == "__main__":main()
