
import threading
import time
from decimal import Decimal, ROUND_DOWN
import requests

token_details_dict = {}

from telebot import types

import telebot
from web3 import Web3
from eth_abi import decode_abi
from eth_utils import decode_hex, encode_hex
from eth_account import Account
import os
from dotenv import load_dotenv
import json
import locale


load_dotenv()

w3 = Web3(Web3.HTTPProvider
('https://rpc.pulsechain.com'))
nodeUrl = 'https://rpc.pulsechain.com'

print(w3.isConnected())
bot = telebot.TeleBot('5815528212:AAGO37n2Sd6qaudMDXrck3AZ6HGsvhf3U4Y', parse_mode=None)
priv_key = os.getenv('PRIVATE_KEY')
PulseXRouterAddy = w3.toChecksumAddress('0x98bf93ebf5c380C0e6Ae8e192A7e2AE08edAcc02')
PulseXFactoryAddy = w3.toChecksumAddress('0x1715a3e4a142d8b698131108995174f37aeba10d')

with open('erc20abi.json') as f:
    erc20abi = json.load(f)
with open('Routerabi.json') as f:
    RouterAbi = json.load(f)
with open('Factoryabi.json') as f:
    FactoryAbi = json.load(f)
with open('PairAbi.json') as f:
    PairAbi = json.load(f)



def get_token_price(token_address,pair):
    pair = pair.lower()
    factory_contract = w3.eth.contract(address=PulseXFactoryAddy, abi=FactoryAbi)
    router_contract = w3.eth.contract(address=PulseXRouterAddy, abi=RouterAbi)
    stable_address = w3.toChecksumAddress('0xefD766cCb38EaF1dfd701853BFCe31359239F305')
    wpls_address = w3.toChecksumAddress('0xA1077a294dDE1B09bB078844df40758a5D0f9a27')
    token_address = w3.toChecksumAddress(token_address)

    url = 'https://graph.pulsechain.com/subgraphs/name/pulsechain/pulsex'
    headers = {'Content-Type': 'application/json'}
    query = f"""
    {{
      pairDayDatas(
          where: {{
            pairAddress: "{pair}",
            date_gt: 0
          }}) {{
        reserve0
        reserve1
        token1 {{
            id
        }}
        token0 {{
            id
        }}
      }}
    }}
    """ 

    # Send POST request
    r = requests.post(url, headers=headers, data=json.dumps({'query': query}))

    # Parse response
    data = json.loads(r.text)
    pair_day_data = data['data']['pairDayDatas']
    latest_entry = pair_day_data[-1]
    reserve0 = float(latest_entry['reserve0'])
    reserve1 = float(latest_entry['reserve1'])
    token0 = str(latest_entry['token0']['id'])
    token1 = str(latest_entry['token1']['id'])
    token0 = w3.toChecksumAddress(token0)
    token1 = w3.toChecksumAddress(token1)



    if token0 == token_address:
        token_reserve = reserve0
        wpls_reserve = reserve1
    elif token1 == token_address:
        token_reserve = reserve1
        wpls_reserve = reserve0
    else:
        return None

    
    token_price_wpls = wpls_reserve / token_reserve 
    wpls_price_stable = router_contract.functions.getAmountsOut(w3.toWei(1, 'Ether'), [wpls_address, stable_address]).call()[1] / 10**18
    token_price_stable = token_price_wpls * wpls_price_stable
    return token_price_stable



def get_market_cap(token_address,pair):
    token_address = w3.toChecksumAddress(token_address)

    # Get token supply and price
    token_supply = get_token_supply(token_address)
    token_price = get_token_price(token_address,pair)


    if token_supply is None:
        return (f"Couldn't retrieve token supply information for {token_address}")
    elif token_price is None:

        return (f"Couldn't retrieve token price information for {token_address}")
        

    # Get market cap in USD
    market_cap = token_supply * token_price / 10**18
    
    # Set locale to en_US to format numbers with comma separator and 2 decimal places
    locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')

    # Format market cap as USD amount with commas and no decimal places if under 1000, otherwise show 2 decimal places
    if market_cap < 1000:
        market_cap_formatted = locale.format_string("%d", market_cap, grouping=True)
    else:
        market_cap_formatted = locale.currency(market_cap, symbol=True, grouping=True, international=False)
    return market_cap_formatted


# Get the transfer fee percentage for a given token contract address

def get_token_owner(token_address):

    token_address = w3.toChecksumAddress(token_address)
    token_contract = w3.eth.contract(address=token_address, abi=erc20abi)
    try:
        owner = token_contract.functions.owner().call()
    except ValueError:
        # If calling the owner function raises a ValueError, it indicates that the function doesn't exist
        url = f"https://scan.pulsechain.com/api?module=account&action=txlist&address={token_address}"

        response = requests.get(url)
        data = response.json()
        owner = data['result'][0]['from']

        

        
    if owner == '0x0000000000000000000000000000000000000000' or owner == '0x000000000000000000000000000000000dead':
        owner = '*RENOUNCED*'

    return owner
def check_contract_links(contract_address):
    try:

            contract_address = w3.toChecksumAddress(contract_address)
            telegram_links = []
            twitter_links = []
            website_links = []
            # Get the contract metadata
            source_code = get_token_verification(contract_address)[1]
            # Check for Twitter links
            twitter_links = [link for link in source_code.split() if link.startswith("https://twitter.com")]

            # Check for Telegram links
            telegram_links = [link for link in source_code.split() if link.startswith("https://t.me")]

            # Check for website links
            website_links = [link for link in source_code.split() if link.startswith("https://") and not link.startswith(("https://twitter.com", "https://t.me", "https://github.com"))]

            return twitter_links, telegram_links, website_links

    except Exception as e:
        print(e)
        return None


def check_honeypot_and_get_tax(token_address):
    provider = Web3.HTTPProvider("http://127.0.0.1:8545")
    w3 = Web3(provider)
    token_address = w3.toChecksumAddress(token_address)
    token_contract = w3.eth.contract(address=token_address, abi=erc20abi)
    factory_contract = w3.eth.contract(address=PulseXFactoryAddy, abi=FactoryAbi)
    router_contract = w3.eth.contract(address=PulseXRouterAddy, abi=RouterAbi)
    wpls_address = w3.toChecksumAddress('0xA1077a294dDE1B09bB078844df40758a5D0f9a27')
    pair_address = factory_contract.functions.getPair(token_address, wpls_address).call()
    pair_contract = w3.eth.contract(address=pair_address, abi=PairAbi)

    # Specify the addresses and ETH amount
    sender_address = "0xdF3e18d64BC6A983f673Ab319CCaE4f1a57C7097"
    eth_amount = Web3.toWei(2, 'ether')  # 1 ETH


    try:    # Step 1: Get the expected token amount for the given ETH amount
        amounts_out = router_contract.functions.getAmountsOut(eth_amount, [wpls_address, token_address]).call()
        expected_token_amount = amounts_out[1]

            # Step 2: Perform a buy on the router to get the actual amount of tokens received
        buy_transaction = router_contract.functions.swapExactETHForTokens(
                0, [wpls_address, token_address], sender_address, int(time.time()) + 1000
        ).buildTransaction({'gasPrice': w3.eth.gas_price, 'chainId': 31337, 'from': sender_address, 'value': eth_amount, 'nonce': w3.eth.get_transaction_count(sender_address)})
        buy_signed_tx = w3.eth.account.sign_transaction(buy_transaction, private_key=priv_key)
            
        buy_tx_hash = w3.eth.send_raw_transaction(buy_signed_tx.rawTransaction)

            # Wait for the transaction to be mined
        buy_tx_receipt = w3.eth.wait_for_transaction_receipt(buy_tx_hash)

            # Extract the actual amount of tokens received from the receipt
        logs = buy_tx_receipt['logs']
        actual_token_amount = 0
        for log in logs:
                if log['address'] == token_address:
                    actual_token_amount += int(log['data'], 16)
            # Step 3: Calculate the transfer tax for the buy transaction
        buy_transfer_tax = ((expected_token_amount - actual_token_amount) / expected_token_amount) * 100
        


            # Step 4: Approve the router contract to spend the token on behalf of the sender
        approve_amount = actual_token_amount  # Approve the full token balance
        approve_tx = token_contract.functions.approve(router_contract.address, approve_amount).buildTransaction(
            {'gasPrice': w3.eth.gas_price, 'chainId': 31337, 'from': sender_address, 'nonce': w3.eth.get_transaction_count(sender_address)}
        )
        approve_signed_tx = w3.eth.account.sign_transaction(approve_tx, private_key=priv_key)
        approve_tx_hash = w3.eth.send_raw_transaction(approve_signed_tx.rawTransaction)

        # Wait for the transaction to be mined
        approve_tx_receipt = w3.eth.wait_for_transaction_receipt(approve_tx_hash)

        # Step 5: Perform a sell on the router to swap the token back to ETH
        sell_transaction = router_contract.functions.swapExactTokensForTokens(
            actual_token_amount, 0, [token_address, wpls_address], sender_address, int(time.time()) + 1000
        ).buildTransaction({'gasPrice': w3.eth.gas_price, 'chainId': 31337, 'from': sender_address, 'nonce': w3.eth.get_transaction_count(sender_address)})
        sell_signed_tx = w3.eth.account.sign_transaction(sell_transaction, private_key=priv_key)
        sell_tx_hash = w3.eth.send_raw_transaction(sell_signed_tx.rawTransaction)

        # Wait for the transaction to be mined
        sell_tx_receipt = w3.eth.wait_for_transaction_receipt(sell_tx_hash)
        eth_received = sell_tx_receipt['logs'][2]['data']
        gas_used_buy = buy_tx_receipt['gasUsed']
        gas_used_sell = sell_tx_receipt['gasUsed']
        formatted_gas_used_buy = '{:,}'.format(gas_used_buy)
        formatted_gas_used_sell = '{:,}'.format(gas_used_sell)




        # Read the value of Ether sent in the transaction
        eth_received = int(eth_received, 16) / 1e18  # Convert hex to decimal and then to ETH


        # Step 6: Calculate the transfer tax for the sell transaction
        amounts_in = router_contract.functions.getAmountsIn(actual_token_amount, [wpls_address, token_address]).call()
        expected_token_amount_sell = amounts_in[0] / 10 ** 18

        sell_transfer_tax = (expected_token_amount_sell - eth_received) / expected_token_amount_sell * 100
        if sell_transfer_tax <= 0.5792590000000015:
                sell_transfer_tax = 0.0


        # If the transfer succeeds without throwing an exception, it's not a Honeypot
        return True, buy_transfer_tax, sell_transfer_tax, formatted_gas_used_buy, formatted_gas_used_sell


    except Exception as e:  
        print(f"Error occurred during transaction: {e}")
        return False, None, None, None, None




def get_token_holders(contract_address):
    url = f"https://scan.pulsechain.com/api?module=token&action=getTokenHolders&contractaddress={contract_address}&page=0&offset=9999"

    response = requests.get(url)
    data = response.json()
    holders = data['result']
    total_supply = get_token_supply(contract_address)  # Replace with the actual total supply of the token
    top_three_holders = holders[:3]

    percentages = []
    for holder in top_three_holders:
        value = int(holder['value'])
        percentage = (value / total_supply) * 100
        percentages.append(f"{percentage:.2f}%")

    number_of_holders = len(holders)

    return number_of_holders, ", ".join(percentages)




def get_token_liquidity(token_address,pair):
    try:
        pair = pair.lower()    
        # Query parameters
        url = 'https://graph.pulsechain.com/subgraphs/name/pulsechain/pulsex'
        headers = {'Content-Type': 'application/json'}
        query = f"""
        {{
        pairDayDatas(
            where: {{
                pairAddress: "{pair}",
                date_gt: 0
            }}), {{ 
            reserveUSD
            }}
        
        }}
        """ 

        # Send POST request
        r = requests.post(url, headers=headers, data=json.dumps({'query': query}))

        # Parse response
        data = json.loads(r.text)
        pair_day_data = data['data']['pairDayDatas'][-1]
        liquidity = float(pair_day_data['reserveUSD'])    # Get token price in USD
        # Calculate market cap in USD
        market_cap = liquidity / 2
    
        # Set locale to en_US to format numbers with comma separator and 2 decimal places

        return market_cap
    except IndexError as e:
        print(e)
        return None

def get_token_supply(contract_address):
    try:
        contract_address = contract_address.lower()
        url = f'https://scan.pulsechain.com/api?module=stats&action=tokensupply&contractaddress={contract_address}'


        response = requests.get(url)
        data = response.json()
        total_supply = data['result']
        return int(total_supply)
    except Exception as e:
        return None

        

def get_token_name(contract_address):
    # Create a contract instance

    contract = w3.eth.contract(address=w3.toChecksumAddress(contract_address), abi=erc20abi)

    # Call the `totalSupply()` function
    name = contract.functions.name().call()

    return name
def get_pair_address(token_address):
    wpls_address = w3.toChecksumAddress('0xA1077a294dDE1B09bB078844df40758a5D0f9a27')
    token_address = w3.toChecksumAddress(token_address)
    factory_contract = w3.eth.contract(address=PulseXFactoryAddy, abi=FactoryAbi)
    pair_address = factory_contract.functions.getPair(token_address, wpls_address).call()
    return pair_address

def get_token_symbol(token_address):
    token_address = w3.toChecksumAddress(token_address)
    token_contract = w3.eth.contract(address=token_address, abi=erc20abi)
    symbol = token_contract.functions.symbol().call()
    return symbol
def get_contract_age(contract_address):
    try:
        contract_address = contract_address.lower()

        currentblock = w3.eth.blockNumber

        deployer,creation_block = get_token_deployer(contract_address)

        # Calculate the difference in blocks and convert to seconds
        block_difference = currentblock - int(creation_block)
        total_seconds = block_difference * 15  # approx. 15 seconds per block

        # Conversion constants
        seconds_in_a_minute = 60
        seconds_in_an_hour = 60 * seconds_in_a_minute
        seconds_in_a_day = 24 * seconds_in_an_hour
        seconds_in_a_week = 7 * seconds_in_a_day
        seconds_in_a_month = 30 * seconds_in_a_day  # approximate
        seconds_in_a_year = 365 * seconds_in_a_day  # not accounting for leap years

        # Convert to various time units
        total_seconds = float(total_seconds)
        
        years = total_seconds // seconds_in_a_year
        total_seconds %= seconds_in_a_year

        months = total_seconds // seconds_in_a_month
        total_seconds %= seconds_in_a_month

        weeks = total_seconds // seconds_in_a_week
        total_seconds %= seconds_in_a_week

        days = total_seconds // seconds_in_a_day
        total_seconds %= seconds_in_a_day

        hours = total_seconds // seconds_in_an_hour
        total_seconds %= seconds_in_an_hour

        minutes = total_seconds // seconds_in_a_minute
        total_seconds %= seconds_in_a_minute

        # Build time string
        contract_age = ""

        if years > 0:
            contract_age += f"{int(years)}Y "
            
        if months > 0:
            contract_age += f"{int(months)}M "
        if weeks > 0:
            contract_age += f"{int(weeks)}W "
        if days > 0:
            contract_age += f"{int(days)}D "
        if hours > 0:
            contract_age += f"{int(hours)}H "
        if minutes > 0:
            contract_age += f"{int(minutes)}M"

        # Remove trailing space
        contract_age = contract_age.rstrip()

        return contract_age,deployer

    except Exception as e:
        print(e)
        return None
def get_24hr_volume(pair_id):
    pair_id = pair_id.lower()
    url = 'https://graph.pulsechain.com/subgraphs/name/pulsechain/pulsex'  # Change this to the actual endpoint if it's different
    query = f"""
    {{
      pairDayDatas(
          where: {{
            pairAddress: "{pair_id}",
            date_gt: 0
          }}) {{

				dailyVolumeUSD
      }}
         
      
    }}
    """
    response = requests.post(url, json={'query': query})
    data = json.loads(response.text)
    pair_day_data = data['data']['pairDayDatas'][-1]
    volume = float(pair_day_data['dailyVolumeUSD'])   
    if volume >= 1_000_000_000:
        return f'{volume / 1_000_000_000:.1f}M'
    elif volume >= 1_000_000:
        return f'{volume / 1_000_000:.1f}M'
    elif volume >= 1_000:
        return f'{volume / 1_000:.1f}K'
    else:
        return f'{volume:.0f}$'

def get_token_verification(contract_address):
    try:
        contract_address = contract_address.lower()
        url = 'https://scan.pulsechain.com/graphiql/' # Change this to the actual endpoint if it's different
        query = f"""
        {{address (hash:"{contract_address}") {{
							smartContract {{
							  contractSourceCode
							}}
            


            
        }}}}
        """
        response = requests.post(url, json={'query': query})
        data = json.loads(response.text)

        if 'smartContract' in data['data']['address'] and data['data']['address']['smartContract'] is None:
            return False
        else:
            return True, data['data']['address']['smartContract']['contractSourceCode']
    except ValueError as e: 
        print(e)
        return None

def get_contract_abi(contract_address):
    try:
        if get_token_verification(contract_address):
            url = f"https://scan.pulsechain.com/api?module=contract&action=getabi&address={contract_address}"
            response = requests.get(url)
            response.raise_for_status()  # Raise an exception for non-2xx status codes
            data = response.json()
            return data['result']
        else:
            return False
    except (requests.RequestException, ValueError) as e:
        print("Error:", e)
        return None

def compare_function_names(contract_address):
    try:
        # Read the function names from the file
        contract_address = w3.toChecksumAddress(contract_address)
        with open("functions.txt", 'r') as file:
            function_names = file.read().split(',')

        # Create a Web3 instance

        # Create the contract instance
        contract = w3.eth.contract(address=contract_address, abi=get_contract_abi(contract_address))

        # Get the list of function names from the contract
        contract_function_names = [function.function_identifier for function in contract.all_functions()]
        # Compare the function names
        matching_function_names = set(function_names).intersection(contract_function_names)
        matching_function_names_str = ",".join(matching_function_names)

        return matching_function_names_str
    except Exception as e:
        print("ERROR",e)
        return None

def get_token_deployer(contract_address):
    try:
        contract_address = contract_address.lower()
        url = f'https://scan.pulsechain.com/api?module=account&action=txlist&address={contract_address}&sort=asc&offset=1'

        response = requests.get(url)
        data = response.json()
        from_address_hash = data['result'][0]['from']
        creation_block = data['result'][0]['blockNumber']

        return from_address_hash,creation_block
    except ValueError: 
        return None


@bot.message_handler(func=lambda message: message.text.startswith('0x'))
def handle_message(message):
    
    token = message.text
    if not Web3.isAddress(token):
        bot.reply_to(message, f"Invalid token address {token}. Please enter a valid Ethereum address.")
        return
    try:
        token_contract = w3.eth.contract(address=w3.toChecksumAddress(token), abi=erc20abi)

        token_contract.functions.name().call()
    except:
        bot.reply_to(message, f"{token} is not a valid ERC20 token address.")
        return

    pair = get_pair_address(token)
    keyboard = types.InlineKeyboardMarkup()

    token_details = {
        "name": get_token_name(token),
        "symbol": get_token_symbol(token),
        "pair": get_pair_address(token),
        "owner": get_token_owner(token),
        "holders": get_token_holders(token),
        "supply": get_token_supply(token),
        "liquidity": get_token_liquidity(token, pair),
    }
    token_details_dict[token] = token_details

    if token_details["pair"] == '0x0000000000000000000000000000000000000000' or token_details["liquidity"] == None or float(token_details["liquidity"]) <= 50:
        reply_message = f"<b>{token_details['name']} ({token_details['symbol']})</b>\n\n" \
                        f"<b>Token does not have Liquidity or less than 50$</b>\n\n" \
                        f"<b>{token}</b> \n\n" \
                        f"<a href='https://scan.pulsechain.com/address/{token}'>PulseScan</a>"
    else:          
                threading.Thread(target=calculate_contract_age, args=(token,), daemon=True).start()

                keyboard = types.InlineKeyboardMarkup()
                Refresh_data = f"Refresh:{message.chat.id}:{message.message_id}"
                More_data = f"more_info:{message.chat.id}:{message.message_id}"
                refresh_button = types.InlineKeyboardButton(text="Refresh", callback_data=Refresh_data)
                more_info_button = types.InlineKeyboardButton(text="More Info", callback_data=More_data)
                keyboard.add(refresh_button, more_info_button)
                token_details.update({
                    "price": get_token_price(token, pair),
                    "market_cap": get_market_cap(token, pair),
                    "honeypot_info": check_honeypot_and_get_tax(token),
                    "verified": get_token_verification(token),
                    "volume": get_24hr_volume(pair),
                })
                locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')

                liquidity_formatted = locale.currency(token_details["liquidity"], symbol=True, grouping=True, international=False)
                formatted_price = "{:.{}f}".format(float(token_details['price']), 10)
                formatted_price = formatted_price.rstrip("0").rstrip(".")
                reply_message = f"<b>{token_details['name']} ({token_details['symbol']})</b>\n\n" \
                        f"<b>Network:</b> Pulsechain\n" \
                        f"<b>Price:</b> {formatted_price}\n" \
                        f"<b>Owner:</b> {token_details['owner']}\n" \
                        f"<b>Liquidity (WETH):</b> {liquidity_formatted}\n" \
                        f"<b>MC:</b> {token_details['market_cap']}\n" \
                        f"<b>Volume:</b> {token_details['volume']}\n" \
                        f"<b>Holders:</b> {token_details['holders'][0]}\n" \
                        f"<b>Tax:</b> {token_details['honeypot_info'][1]} | {token_details['honeypot_info'][2]}\n\n" \
                        f"<b>Sellable:</b> {token_details['honeypot_info'][0]}\n\n" \
                        f"<b>{token}</b> \n\n" \
                        f"<a href='https://www.dextools.io/app/en/pulse/pair-explorer/{pair}'>DexTools</a> | " \
                        f"<a href='https://scan.pulsechain.com/address/{token}'>PulseScan</a>"

    bot.reply_to(message, reply_message,reply_markup=keyboard, parse_mode='HTML')

def calculate_contract_age(token):
# Adjust the delay as needed

    # Calculate contract age after a delay
    try:
        age = get_contract_age(token)

        # Update the token_details_dict with the contract age
        token_details_dict[token]["age"] = age
    except Exception as e:
        return None

def get_wpls_price():
    try:
        # Get the PulseX Factory contract
            factory_contract = w3.eth.contract(address=PulseXFactoryAddy, abi=FactoryAbi)
            
            # Get the WPLS and stable coin token addresses
            wpls_address = w3.toChecksumAddress('0xA1077a294dDE1B09bB078844df40758a5D0f9a27')
            stable_address = w3.toChecksumAddress('0xefD766cCb38EaF1dfd701853BFCe31359239F305')

            # Get the pair contract address
            pair_address = factory_contract.functions.getPair(wpls_address, stable_address).call()

            # Get the pair contract
            pair_contract = w3.eth.contract(address=pair_address, abi=PairAbi)

            # Get the WPLS and stable coin reserves from the pair contract
            reserves = pair_contract.functions.getReserves().call()
            wpls_reserve = reserves[0] if wpls_address.lower() == pair_contract.functions.token0().call().lower() else reserves[1]
            stable_reserve = reserves[1] if wpls_address.lower() == pair_contract.functions.token0().call().lower() else reserves[0]

            # Calculate the WPLS price in stable coin
            wpls_price_stable = w3.toWei(stable_reserve, 'Ether') / w3.toWei(wpls_reserve, 'Ether')
            return wpls_price_stable
    except Exception as e:
        print(e)
        return None
def get_wallet_worth(contract_address):
    try:
        url = f"https://scan.pulsechain.com/api?module=account&action=balance&address={contract_address}"

        response = requests.get(url)
        data = response.json()
        result = data['result']
        result = int(result) / 10**18
        result = round(result, 1)  # round to 1 decimal place
        result_dollar = result * float(get_wpls_price())
        result_dollar = round(result_dollar, 1)  # round to 1 decimal place

        return result,result_dollar
    except Exception as e: 
        print(e)
        return None


@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    if "Refresh" in call.data:
        try:
            _, chat_id, message_id = call.data.split(":")


            # Get original message the bot responded to
            original_message = call.message.reply_to_message.text
            token = original_message.split("\n")[0]  # Assuming first line of the message is the token address. Adjust as necessary.
            pair = get_pair_address(token)
            keyboard = types.InlineKeyboardMarkup()

            token_details = {
                "name": get_token_name(token),
                "symbol": get_token_symbol(token),
                "pair": get_pair_address(token),
                "owner": get_token_owner(token),
                "holders": get_token_holders(token),
                "supply": get_token_supply(token),
                "liquidity": get_token_liquidity(token, pair),
            }
            token_details_dict[token] = token_details

            if token_details["pair"] == '0x0000000000000000000000000000000000000000' or token_details["liquidity"] == None or float(token_details["liquidity"]) <= 50:
                reply_message = f"<b>{token_details['name']} ({token_details['symbol']})</b>\n\n" \
                                f"<b>Token does not have Liquidity or less than 50$</b>\n\n" \
                                f"<b>{token}</b> \n\n" \
                                f"<a href='https://scan.pulsechain.com/address/{token}'>PulseScan</a>"
            else:          
                        threading.Thread(target=calculate_contract_age, args=(token,), daemon=True).start()

                        keyboard = types.InlineKeyboardMarkup()
                        Refresh_data = f"Refresh:{chat_id}:{message_id}"
                        More_data = f"more_info:{chat_id}:{message_id}"
                        refresh_button = types.InlineKeyboardButton(text="Refresh", callback_data=Refresh_data)
                        more_info_button = types.InlineKeyboardButton(text="More Info", callback_data=More_data)
                        keyboard.add(refresh_button, more_info_button)
                        token_details.update({
                            "price": get_token_price(token, pair),
                            "market_cap": get_market_cap(token, pair),
                            "honeypot_info": check_honeypot_and_get_tax(token),
                            "verified": get_token_verification(token),
                            "volume": get_24hr_volume(pair),
                        })
                        locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')

                        liquidity_formatted = locale.currency(token_details["liquidity"], symbol=True, grouping=True, international=False)
                        formatted_price = "{:.{}f}".format(float(token_details['price']), 10)
                        formatted_price = formatted_price.rstrip("0").rstrip(".")
                        reply_message = f"<b>{token_details['name']} ({token_details['symbol']})</b>\n\n" \
                                f"<b>Network:</b> Pulsechain\n" \
                                f"<b>Price:</b> {formatted_price}\n" \
                                f"<b>Owner:</b> {token_details['owner']}\n" \
                                f"<b>Liquidity (WETH):</b> {liquidity_formatted}\n" \
                                f"<b>MC:</b> {token_details['market_cap']}\n" \
                                f"<b>Volume:</b> {token_details['volume']}\n" \
                                f"<b>Holders:</b> {token_details['holders'][0]}\n" \
                                f"<b>Tax:</b> {token_details['honeypot_info'][1]} | {token_details['honeypot_info'][2]}\n\n" \
                                f"<b>Sellable:</b> {token_details['honeypot_info'][0]}\n\n" \
                                f"<b>{token}</b> \n\n" \
                                f"<a href='https://www.dextools.io/app/en/pulse/pair-explorer/{pair}'>DexTools</a> | " \
                                f"<a href='https://scan.pulsechain.com/address/{token}'>PulseScan</a>"
        
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,reply_markup=keyboard, text=reply_message, parse_mode='HTML')
        except Exception:
          return None
    elif "more_info" in call.data:
        try:
            _, chat_id, message_id = call.data.split(":")

            # Get original message the bot responded to
            original_message = call.message.reply_to_message.text
            token = original_message.split("\n")[0]  # Assuming first line of the message is the token address. Adjust as necessary.
            pair = get_pair_address(token)
            keyboard = types.InlineKeyboardMarkup()
            Refresh_data = f"Rekresh:{chat_id}:{message_id}"
            back_data = f"brack:{chat_id}:{message_id}"
            telegram_links, twitter_links, website_links = check_contract_links(token)

            refresh_button = types.InlineKeyboardButton(text="Refresh", callback_data=Refresh_data)
            back_button = types.InlineKeyboardButton(text="Back", callback_data=back_data)        
            keyboard.add(refresh_button, back_button)
            token_name = token_details_dict[token]['name']
            token_symbol = token_details_dict[token]['symbol']
            Holders = token_details_dict[token]['holders']
            Verified = token_details_dict[token]['verified']
            Supply = token_details_dict[token]['supply']
            # Create links string
            links = ""
            if telegram_links:
                links += f"<a href='{telegram_links[0]}'>Telegram</a>"
            if twitter_links:
                if links:
                    links += " | "
                links += f"<a href='{twitter_links[0]}'>Twitter</a>"
            if website_links:
                if links:
                    links += " | "
                links += f"<a href='{website_links[0]}'>Website</a>)"
            try:
                age = token_details_dict[token]['age'][0]
                deployer = age = token_details_dict[token]['age'][1]
                Deployer_funds1, Deployer_funds2 = get_wallet_worth(deployer)

            except Exception as e:
                age = None
                deployer = None
                Deployer_funds1 = None
                Deployer_funds2 = None


            reply_message = f"<b>{token_name} ({token_symbol})</b>\n\n" \
                                f"<b>Deployer:</b> {deployer}\n" \
                                f"<b> └─</b> {Deployer_funds1} PLS ({Deployer_funds2}$)\n" \
                                f"<b>Holders:</b> {Holders[0]}\n" \
                                f"<b> └─</b> {Holders[1]} \n" \
                                f"<b>Gas:</b> {token_details_dict[token]['honeypot_info'][3]} | {token_details_dict[token]['honeypot_info'][4]}\n" \
                                f"<b>Supply:</b> {Supply / 10**18}\n" \
                                f"<b>Age:</b> {age}\n" \
                                f"<b>Verified:</b> {Verified[0]}\n\n" \
                                f"<b>Functions:</b> {compare_function_names(token)}\n" \
                                f"<b>Links:</b> {links}\n\n" \
                                f"<b>{token}</b> \n\n" \
                                f"<a href='https://www.dextools.io/app/en/pulse/pair-explorer/{pair}'>DexTools</a> | " \
                                f"<a href='https://scan.pulsechain.com/address/{token}'>PulseScan</a>"

            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=reply_message, reply_markup=keyboard, parse_mode='HTML')
        except Exception:
            return None
    elif "back" in call.data:
        try:
            _, chat_id, message_id = call.data.split(":")
            original_message = call.message.reply_to_message.text
            token = original_message.split("\n")[0]
            token_name = token_details_dict[token]['name']
            token_symbol = token_details_dict[token]['symbol']
            pair = token_details_dict[token]['pair']
            owner = token_details_dict[token]['owner']
            volume = token_details_dict[token]['volume']
            Holders = token_details_dict[token]['holders']


            if pair == '0x0000000000000000000000000000000000000000':
                reply_message = f"<b>{token_name} ({token_symbol})</b>\n\n" \
                                f"<b>Token does not have Liquidity yet</b>\n\n" \
                                f"<b>{token}</b> \n\n" \
                                f"<a href='https://scan.pulsechain.com/address/{token}'>PulseScan</a>"
            else:      
                        keyboard = types.InlineKeyboardMarkup()
                        Refresh_data = f"Refresh:{chat_id}:{message_id}"
                        More_data = f"more_info:{chat_id}:{message_id}"
                        refresh_button = types.InlineKeyboardButton(text="Refresh", callback_data=Refresh_data)
                        more_info_button = types.InlineKeyboardButton(text="More Info", callback_data=More_data)
                        keyboard.add(refresh_button, more_info_button)
                        token_price = token_details_dict[token]["price"]
                        token_liquidity = token_details_dict[token]["liquidity"]
                        market_cap = token_details_dict[token]['market_cap']  
                        sellable, tax1, tax2, buyfee,sellfee = token_details_dict[token]["honeypot_info"]
                        formatted_price = "{:.{}f}".format(float(token_price), 10)
                        formatted_price = formatted_price.rstrip("0").rstrip(".")
                        reply_message = f"<b>{token_name} ({token_symbol})</b>\n\n" \
                                f"<b>Price:</b> {formatted_price}\n" \
                                f"<b>Owner:</b> {owner}\n" \
                                f"<b>Liquidity (WETH):</b> {token_liquidity}$\n" \
                                f"<b>MC:</b> {market_cap}\n" \
                                f"<b>Volume:</b> {volume}\n" \
                                f"<b>Holders:</b> {Holders[0]}\n" \
                                f"<b>Tax:</b> {tax1} | {tax2}\n\n" \
                                f"<b>Sellable:</b> {sellable}\n\n" \
                                f"<b>{token}</b> \n\n" \
                                f"<a href='https://www.dextools.io/app/en/pulse/pair-explorer/{pair}'>DexTools</a> | " \
                                f"<a href='https://scan.pulsechain.com/address/{token}'>PulseScan</a>"

            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,reply_markup=keyboard, text=reply_message, parse_mode='HTML')
        except Exception:
            return None
    elif "Rekresh" in call.data:
        try:
            _, chat_id, message_id = call.data.split(":")

            # Get original message the bot responded to
            original_message = call.message.reply_to_message.text
            token = original_message.split("\n")[0]  # Assuming first line of the message is the token address. Adjust as necessary.
            pair = get_pair_address(token)
            keyboard = types.InlineKeyboardMarkup()
            Refresh_data = f"Rekresh:{chat_id}:{message_id}"
            back_data = f"back:{chat_id}:{message_id}"
            telegram_links, twitter_links, website_links = check_contract_links(token)

            refresh_button = types.InlineKeyboardButton(text="Refresh", callback_data=Refresh_data)
            back_button = types.InlineKeyboardButton(text="Back", callback_data=back_data)        
            keyboard.add(refresh_button, back_button)

            token_details = {
                "name": get_token_name(token),
                "symbol": get_token_symbol(token),
                "holders": get_token_holders(token),
                "age": get_contract_age(token),
                "honeypot": check_honeypot_and_get_tax(token),
                "Supply": get_token_supply(token),
                "verified": get_token_verification(token)
            }
            token_details_dict[token] = token_details
            Holders = token_details_dict[token]['holders']
            token_name = token_details_dict[token]['name']
            token_symbol = token_details_dict[token]['symbol']
            Supply = token_details_dict[token]['Supply']
            Verified = token_details_dict[token]['verified']

            # Create links string
            links = ""
            if telegram_links:
                links += f"<a href='{telegram_links[0]}'>Telegram</a>"
            if twitter_links:
                if links:
                    links += " | "
                links += f"<a href='{twitter_links[0]}'>Twitter</a>"
            if website_links:
                if links:
                    links += " | "
                links += f"<a href='{website_links[0]}'>Website</a>)"
            try:
                age = token_details_dict[token]['age'][0]
                deployer = age = token_details_dict[token]['age'][1]
                Deployer_funds1, Deployer_funds2 = get_wallet_worth(deployer)

            except Exception as e:
                    age = None
                    deployer = None
                    Deployer_funds1 = None
                    Deployer_funds2 = None


            reply_message = f"<b>{token_name} ({token_symbol})</b>\n\n" \
                                f"<b>Deployer:</b> {deployer}\n" \
                                f"<b> └─</b> {Deployer_funds1} PLS ({Deployer_funds2}$)\n" \
                                f"<b>Holders:</b> {Holders[0]}\n" \
                                f"<b> └─</b> {Holders[1]} \n" \
                                f"<b>Gas:</b> {token_details_dict[token]['honeypot'][3]} | {token_details_dict[token]['honeypot'][4]}\n" \
                                f"<b>Supply:</b> {Supply / 10**18}\n" \
                                f"<b>Age:</b> {age}\n" \
                                f"<b>Verified:</b> {Verified[0]}\n\n" \
                                f"<b>Functions:</b> {compare_function_names(token)}\n" \
                                f"<b>Links:</b> {links}\n\n" \
                                f"<b>{token}</b> \n\n" \
                                f"<a href='https://www.dextools.io/app/en/pulse/pair-explorer/{pair}'>DexTools</a> | " \
                                f"<a href='https://scan.pulsechain.com/address/{token}'>PulseScan</a>"

            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=reply_message, reply_markup=keyboard, parse_mode='HTML')
        except Exception:
            return None
bot.polling()
