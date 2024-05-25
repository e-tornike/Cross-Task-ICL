import pandas as pd
import os
import openai
from utils.data import load_prompts
import argparse
from tqdm import tqdm
from openai.error import InvalidRequestError
from utils.data import Tasks
from transformers import AutoModelForCausalLM,AutoTokenizer
import torch
from tqdm import tqdm


def make_prompt(source_prompts,source_instruction,target_prompts,target_instruction,k, task_demo='',demo=False):
    demonstration_part=''
    if demo:
        demonstration_part='Definition: '+source_instruction+'\n'+"\n".join(source_prompts[:k])+'\n'
    input_part='Definition: '+target_instruction+'\n'+task_demo+target_prompts
    
    return demonstration_part+input_part

def run_few_shot_sim(source_dataset_name,target_dataset_name,k=1,method='totally-cross-sim', main_dir = 'results'):


    ###### Load model #####

    os.environ['AZURE_OPENAI_ENDPOINT'] = "https://kglm.openai.azure.com/"
    os.environ['AZURE_OPENAI_KEY'] = "####" #use your key
    deployment_name='kglm-text-davinci-003'
    openai.api_key = os.getenv("AZURE_OPENAI_KEY")
    openai.api_base = os.getenv("AZURE_OPENAI_ENDPOINT") # your endpoint should look like the following https://YOUR_RESOURCE_NAME.openai.azure.com/
    openai.api_type = 'azure'
    openai.api_version = '2023-05-15' # this may change in the future

    ###########

    result_dir = os.path.join(main_dir, f"dataset_name={target_dataset_name}")

    if not os.path.exists(result_dir):
        os.makedirs(result_dir)
    
    ############ load dataset ############
    target_dataset = load_prompts(target_dataset_name,'target-psudo-prompts') 
    
    if 'cross' in method:
        demo=True
        prompts_dataset=target_dataset['all_possible_pairs'][source_dataset_name]
    else:
        demo=False 
        prompts_dataset=target_dataset['all_possible_pairs']['sst2']#sst2 will not be used its a placeholder as load_prompts needs a valid target_dataset_name
    
    target_instructions=target_dataset['instruction-target']
    source_instructions=prompts_dataset['instruction-source'] 
    a=Tasks()    
    if 'in' in method:
        task_demo=a.get_one_example(target_dataset_name)
    else:
        task_demo=''
    

    
    ############

    

    ids=[]
    target_instructions_list = []
    target_input_list=[]
    gold_labels=[]
    prediction_list=[]
    
    for data in tqdm(prompts_dataset['prompts'],desc=f"Evaluating {target_dataset_name} with Source {source_dataset_name}"):
        few_shot_prompt= make_prompt(
            source_prompts=data['source-demonstrations'],
            source_instruction=source_instructions,
            target_prompts=data['target-input'],
            target_instruction=target_instructions,
            k=k,
            task_demo=task_demo,
            demo=demo)
        #print(few_shot_prompt)
        
        #######
        
        try:
            response = openai.Completion.create(engine=deployment_name, prompt=few_shot_prompt, max_tokens=10, temperature = 0.0, stop=['\n'])
            prediction = response['choices'][0]['text']
        except InvalidRequestError:
            
            prediction='<Junk-answer>'
        #######
        ids.append(data['id'])
        target_instructions_list.append(target_instructions)
        target_input_list.append(data['target-input'])
        if type(data['label']) is list:
            gold_labels.append(data['label'][0])
        else:
            gold_labels.append(data['label'])
        prediction_list.append(prediction)        
        #break
    
    return ids,target_instructions_list,target_input_list,gold_labels,prediction_list
    
        
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--target_dataset_name',required=True, type=str)
    parser.add_argument('--make_psudo',action='store_true')
    parser.add_argument('--k', default=1,type=int)
    parser.add_argument('--k_input', default=1,type=int)
    parser.add_argument('--y_psudo', default='psudo-label',type=str)
    parser.add_argument('--seed', default=32,type=int)
    args = parser.parse_args()
    
    model_name = 'kglm_text_davinci_003'
    path=f'data/{args.target_dataset_name}-labeled-model={model_name}.csv' 
    
    if args.make_psudo:
        
        method='totally-cross-sim'
        
        source_tasks=[
            'ag_news',
            'ARC-Easy',
            'boolq',
            'commonsense_qa',
            'conll2003_pos',
            'conll2003_ner',
            'mnli',
            'qqp',
            'race',
            'sst2'
            ]
        
        for s in tqdm(source_tasks,desc='Making Psudo Label from each datapoint'):
            ids,target_instructions_list,target_input_list,gold_labels,prediction_list=run_few_shot_sim(s,args.target_dataset_name,args.k,method)
            
            if not os.path.exists(path):
                eval_dic=dict()
                eval_dic['id']=ids
                eval_dic['instructions']=target_instructions_list
                eval_dic['target_input']=target_input_list
                eval_dic['true_label']=gold_labels
                eval_dic[s]=prediction_list
                result_df=pd.DataFrame(eval_dic)
            else:
                result_df=pd.read_csv(path)
                result_df[s]=prediction_list
            result_df.to_csv(path,index=False)
        
        method='zero-shot'
        ids,target_instructions_list,target_input_list,gold_labels,prediction_list=run_few_shot_sim(s,args.target_dataset_name,0,method)
        result_df=pd.read_csv(path)
        result_df['zero-shot']=prediction_list
        
        pred=result_df.loc[:,source_tasks]
        result_df['psudo-label']=pred.mode(axis=1)[0]
        result_df.to_csv(path,index=False)
        
        exit()
    
    ###### Load model #####

    os.environ['AZURE_OPENAI_ENDPOINT'] = "https://kglm.openai.azure.com/"
    os.environ['AZURE_OPENAI_KEY'] = "060db6b6c3ff468ca2215e0ef75b9cc1"
    deployment_name='kglm-text-davinci-003'
    openai.api_key = os.getenv("AZURE_OPENAI_KEY")
    openai.api_base = os.getenv("AZURE_OPENAI_ENDPOINT") # your endpoint should look like the following https://YOUR_RESOURCE_NAME.openai.azure.com/
    openai.api_type = 'azure'
    openai.api_version = '2023-05-15' # this may change in the future

    model_name = deployment_name.replace("-","_")
    ###########
    
    result_df=pd.read_csv(path)
    
    result_df=result_df.sample(n=args.k_input,random_state=args.seed).reset_index()
    instructions=result_df.loc[0,'instructions']
    c=instructions+'\n'
    
    for i in range(len(result_df)):
        
        
        input=result_df.loc[i, "target_input"]
        y_psudo=str(result_df.loc[i, args.y_psudo])
        
        c+=input+y_psudo+'\n'
    
    target_dataset = load_prompts(args.target_dataset_name,'target-prompts')
    prompts_dataset=target_dataset['all_possible_pairs']['sst2']#sst2 will not be used its a placeholder as load_prompts needs a valid target_dataset_name
    
    ids=[]
    prompts = []
    preds=[]
    gold_labels=[]
    
    
    for data in tqdm(prompts_dataset['prompts'],desc=f"Evaluating {args.target_dataset_name}"):
        few_shot_prompt=c+data['target-input']
        #print(few_shot_prompt)
        
        #######
        
        try:
            response = openai.Completion.create(engine=deployment_name, prompt=few_shot_prompt, max_tokens=10, temperature = 0.0, stop=['\n'])
            prediction = response['choices'][0]['text']
        except InvalidRequestError:
            
            prediction='<Junk-answer>'
        #######

        ids.append(data['id'])
        if type(data['label']) is list:
            gold_labels.append(data['label'][0])
        else:
            gold_labels.append(data['label'])
        prompts.append(few_shot_prompt)
        preds.append(prediction)
        #break
    
    eval_dic=dict()
    eval_dic['id']=ids
    eval_dic['prompt']=prompts
    eval_dic['pred']=preds
    eval_dic['true_label']=gold_labels
    
    result_dir = os.path.join('results', f"dataset_name={args.target_dataset_name}")

    if not os.path.exists(result_dir):
        os.makedirs(result_dir)    
    result_path= os.path.join(result_dir, f"psudo-iclseed={args.seed}-model={model_name}-method={args.y_psudo}-shots={args.k_input}.csv")
    result_df=pd.DataFrame(eval_dic)
    result_df.to_csv(result_path,index=False)

