FROM python:3.11
 
WORKDIR /code

COPY requirements.txt /code/requirements.txt

RUN pip install --upgrade -r /code/requirements.txt

COPY . /code/server

CMD ["uvicorn", "server.main:app", "--reload", "--host", "0.0.0.0", "--port", "80"]
