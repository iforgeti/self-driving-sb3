

# Description
this repository is the part of thesis project "" 
The goal is to train a left-lane side autonomous driving car on a custom map (AIT).

## install carla ... 
[Instructions for installing CARLA ...]
## test env
```
python test_env.py --map_name MapName --level 1 --eps 5 --seed 1234 --mode auto
```
example
```
python test_env.py --mode auto --level 0
```
```
python test_env.py --mode manual --level 0
```
## train

note: 
model_config have to add in config/algorithm_config.py to available to choose or just pass config directly to command line
can continue training by select the load_model
example

## eval
```
python eval.py model_path --level 2 --eps 5 --seed 1234 --record

```

example
```

```

## how to experiment on custom route, map, more
[Instructions for installing CARLA ...]
## not implement yet, todo
* more complex model like transformer 
* pedestrian
## note
* not suppoprt tensorrt yet

# Credit
https://github.com/alberto-mate/CARLA-SB3-RL-Training-Environment  
https://github.com/idreesshaikh/Autonomous-Driving-in-Carla-using-Deep-Reinforcement-Learning.git  
https://github.com/CppMaster/SC2-AI.git  
Mr.Siraphop..
