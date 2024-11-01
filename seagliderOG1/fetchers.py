import pooch
import xarray as xr
import os
from bs4 import BeautifulSoup
import requests
import numpy as np

# Comment 2024 Oct 30: I needed an initial file list to create the registry
# This is impractical for expansion, so may need to move away from pooch.
# This was necessary to get an initial file list
# mylist = fetchers.list_files_in_https_server(server)
# fetchers.create_pooch_registry_from_directory("/Users/eddifying/Dropbox/data/sg015-ncei-download/")


def load_sample_dataset(dataset_name="p0150500_20050213.nc"):
    if dataset_name in data_source_og.registry.keys():
        file_path = data_source_og.fetch(dataset_name)
        return xr.open_dataset(file_path)
    else:
        msg = f"Requested sample dataset {dataset_name} not known"
        raise ValueError(msg)
    
def load_dataset(source, start_profile=None, end_profile=None):
    """
    Load datasets from either an online source or a local directory, optionally filtering by profile range.

    Parameters:
    source (str): The URL to the directory containing the NetCDF files or the path to the local directory.
    start_profile (int, optional): The starting profile number to filter files. Defaults to None.
    end_profile (int, optional): The ending profile number to filter files. Defaults to None.

    Returns:
    xarray.Dataset: A concatenated xarray.Dataset object loaded from the filtered NetCDF files.
    """
    if source.startswith("http://") or source.startswith("https://"):
        # Create a Pooch object to manage the remote files
        data_source_online = pooch.create(
            path=pooch.os_cache("seagliderOG1_online"),
            base_url=source,
            registry=None,
        )

        # List all files in the URL directory
        file_list = list_files_in_https_server(source)
    elif os.path.isdir(source):
        file_list = os.listdir(source)
    else:
        raise ValueError("Source must be a valid URL or directory path.")

    def repeat_trajectory_vars(ds):

        trajectory_var = ds['trajectory'].values
        trajectory_comment = ds['trajectory'].attrs['comment']
        ds['trajectory'] = (['sg_data_point'], np.full(ds.dims['sg_data_point'], np.nan))
        ds['trajectory'][:] = trajectory_var

        ds['trajectory'].attrs['comment'] = trajectory_comment
        return ds

    filtered_files = []
    datasets = []

    for file in file_list:
        if file.endswith(".nc"):
            profile_number = int(file.split("_")[0][4:])
            if start_profile is not None and end_profile is not None:
                if start_profile <= profile_number <= end_profile:
                    filtered_files.append(file)
            elif start_profile is not None:
                if profile_number >= start_profile:
                    filtered_files.append(file)
            elif end_profile is not None:
                if profile_number <= end_profile:
                    filtered_files.append(file)
            else:
                filtered_files.append(file)

    for file in filtered_files:
        if source.startswith("http://") or source.startswith("https://"):
            ds = load_sample_dataset(file)
        else:
            ds = xr.open_dataset(os.path.join(source, file))
        
        # drop all dimensions other than sg_data_point
        ds = repeat_trajectory_vars(ds)
        ds = add_gps_coordinates(ds)
        ds_sg_data_point = ds.drop_dims(set(ds.dims).difference(["sg_data_point"])) 
        datasets.append(ds_sg_data_point)

    ds_all = xr.concat(datasets, dim="sg_data_point")
    ds_all = ds_all.sortby("ctd_time")

    return ds_all

def add_gps_coordinates(ds):
    # Find the nearest index in sg_data_point corresponding to gps_time
    def find_nearest_index(ds, gps_time):
        time_diff = np.abs(ds['ctd_time'] - gps_time)
        nearest_index = time_diff.argmin().item()
        return nearest_index

    # Create new variables gps_lat and gps_lon with dimensions sg_data_point
    ds['gps_lat'] = (['sg_data_point'], np.full(ds.dims['sg_data_point'], np.nan))
    ds['gps_lon'] = (['sg_data_point'], np.full(ds.dims['sg_data_point'], np.nan))
    ds['gps_time'] = (['sg_data_point'], np.full(ds.dims['sg_data_point'], np.nan))

    # Fill gps_lat and gps_lon with values from log_gps_lat and log_gps_lon at the nearest index
    for gps_time, gps_lat, gps_lon in zip(ds.log_gps_time.values, ds.log_gps_lat.values, ds.log_gps_lon.values):
        nearest_index = find_nearest_index(ds, gps_time)
        ds['gps_lat'][nearest_index] = gps_lat
        ds['gps_lon'][nearest_index] = gps_lon
        ds['gps_time'][nearest_index] = gps_time
    return ds

def extract_non_sg_data_point_vars(ds):
    """
    Extract variables from an xarray dataset that do not have the 'sg_data_point' dimension.
    Parameters:
    ds (xarray.Dataset): The input xarray dataset containing various variables.
    Returns:
    xarray.Dataset: A new xarray dataset containing only the variables that do not have the 'sg_data_point' dimension.
    """
    # Create a dictionary to hold the new variables
    new_vars = {}
    
    # Iterate over the variables in the dataset
    for var_name, var_data in ds.data_vars.items():
        # Check if the variable has a different dimension from 'sg_data_point'
        if 'sg_data_point' not in var_data.dims:
            new_vars[var_name] = var_data
    
    # Create a new xarray dataset with the extracted variables
    new_ds = xr.Dataset(new_vars)
    
    return new_ds


def list_files_in_https_server(url):
    """
    List files in an HTTPS server directory using BeautifulSoup and requests.

    Parameters:
    url (str): The URL to the directory containing the files.

    Returns:
    list: A list of filenames found in the directory.
    """
    response = requests.get(url)
    response.raise_for_status()  # Raise an error for bad status codes

    soup = BeautifulSoup(response.text, "html.parser")
    files = []

    for link in soup.find_all("a"):
        href = link.get("href")
        if href and href.endswith(".nc"):
            files.append(href)

    return files


def create_pooch_registry_from_directory(directory):
    """
    Create a Pooch registry from files in a specified directory.

    Parameters:
    directory (str): The path to the directory containing the files.

    Returns:
    dict: A dictionary representing the Pooch registry with filenames as keys and their SHA256 hashes as values.
    """
    registry = {}
    files = os.listdir(directory)

    for file in files:
        if file.endswith(".nc"):
            file_path = os.path.join(directory, file)
            sha256_hash = pooch.file_hash(file_path, alg="sha256")
            registry[file] = f"sha256:{sha256_hash}"

    return registry



# Example usage
#directory_path = "/Users/eddifying/Dropbox/data/sg015-ncei-snippet"
#pooch_registry = create_pooch_registry_from_directory(directory_path)
#print(pooch_registry)


server = "https://www.dropbox.com/scl/fo/dhinr4hvpk05zcecqyz2x/ADTqIuEpWHCxeZDspCiTN68?rlkey=bt9qheandzbucca5zhf5v9j7a&dl=0"
server = "https://www.ncei.noaa.gov/data/oceans/glider/seaglider/uw/015/20040924/"
data_source_og = pooch.create(
    path=pooch.os_cache("seagliderOG1"),
    base_url=server,
    registry={
        # Data originate here: https://www.ncei.noaa.gov/access/metadata/landing-page/bin/iso?id=gov.noaa.nodc:0111844
        # Generated on Mac OSX using shasum -a 256 p0150500_20050213.nc
        "p0150500_20050213.nc": "sha256:b2eae4849b95ed9bc16a5f0eb6cb3c58679ea4e0e8b2a69881e80b5171774ff8",
        "p0150501_20050213.nc": "sha256:66c6df815a578b918f1663ccbead265a2fbe3da55b8996437d4a7915264b38a4",
        "p0150502_20050214.nc": "sha256:6a2b7c8abe532610c861eedafd74c56f7b876a6c4bf67c71e443b266c83cbc11",
        "p0150503_20050214.nc": "sha256:4398ba6bb5c89afde675695bdef6ace016f2a1bdc2a1f32e3d761cae13ca6eca",
        "p0150504_20050215.nc": "sha256:ab1cde8d3a5f8a639fa323906dd7b9d287341b3cd6456c4e1cb70ed6a7c1d60e",
        "p0150317_20041209.nc": "sha256:f3c0d11028a2e3ef91ce8bd71992216667c4a817d78ad8ebc61f415f94f29285",
        "p0150041_20040930.nc": "sha256:cb2de268c0d7c24d603f4f195d9c94266684b0ba57f57c37f812be469ec4acf0",
        "p0150081_20041009.nc": "sha256:9d014ce40e31e949d70e8f89c0e2f80f583fd5382899a567941ee905b104451e",
        "p0150563_20050310.nc": "sha256:4fedd76a05c45f7b7e374f8c4c485b69bd4fa3cd67de934b765dcfe27b8a3ef1",
        "p0150372_20041229.nc": "sha256:93d70544d454c8e5e19dbda63219b4d331b20ed6eeef389fabc21d8f0d42f8a9",
        "p0150553_20050306.nc": "sha256:13bbbf551ed94cceaeca5e9a993410672e9d1138533098504a23e9de49d39edc",
        "p0150508_20050216.nc": "sha256:026c54397237b2f612be66f5c3dfb2da22bb89c2804c9295d8833a93a60f21c3",
        "p0150039_20040929.nc": "sha256:f58466a35b39e4616a4611f34cb0f84678df09c8ebf1ac70d42cc1e6fa4aa904",
        "p0150168_20041027.nc": "sha256:60dd3cc26e5bd8285145156b6875512233ec680d0479e644967541a92d6652d1",
        "p0150195_20041102.nc": "sha256:dbaf97f7e30e3c9c6da0c1cddc468fdfd3962aa8c2c6b361d0c93afc02d9febb",
        "p0150089_20041010.nc": "sha256:2490c7f27642b26e48a927f3a710c01ba7f0b50bf420027e4d360511a49acec7",
        "p0150414_20050112.nc": "sha256:dfee5687dd5f1fd17638c48901bf1842ae661ce815fc837fc319aab97ef53787",
        "p0150061_20041004.nc": "sha256:763c872a5a7e6f625ce2c54a4e75f3eb88a6730fddc5ea035ff599cf5b161eaa",
        "p0150506_20050215.nc": "sha256:bdddb8b4592e7352055d5b171e8bf5dd0c4bd7e69532f929b59b5c8c10b6aabb",
        "p0150478_20050205.nc": "sha256:0f707892ad4ddb7814694520226a8e2c1f323e3ff6c1d267c4d36b895e7e1843",
        "p0150131_20041020.nc": "sha256:158f673ab58b287a6d90b20fedab234f828334b7f06c4a0ce08cf2050d91dfdf",
        "p0150214_20041106.nc": "sha256:fb56eef469a1c23e7318b30f03ef3bf58e621269b7c6c3cfef1e56559b11ae8e",
        "p0150592_20050321.nc": "sha256:03045ca092ec5f0da8266ed01a0ca90916334dd0887ee5fe79f697267937e0f1",
        "p0150064_20041005.nc": "sha256:ffede2fc5d64863550d0867118f3a5192585871ab506a4f15dd0d2730e538cf2",
        "p0150566_20050311.nc": "sha256:a52086b57a13cc3ae73a9c968218ffd18e31ba2b15d1c5632e53008b4db5b707",
        "p0150556_20050307.nc": "sha256:5ade6cf881e25c2cab871c4c8a5345c5f69200231290cbabf081c42f55ea5d1b",
        "p0150282_20041125.nc": "sha256:38fb8ae4f0180176434989d23fb87a5013a0fefe40a3a58df981075b4339ccd5",
        "p0150114_20041016.nc": "sha256:55f909abbf867c20c2016d0e2db58d7b524a7b3cefd6c9235f8b5b62c67c672c",
        "p0150079_20041008.nc": "sha256:dff40fc01e2e3b686e2c15f83413e7136ad50d993ad4457ce6791c5bc211c31c",
        "p0150364_20041226.nc": "sha256:c3f2e6be3e4553dcf657b439271b081c4bbe5b0c154cca8f6662b467fa3d0a48",
        "p0150236_20041113.nc": "sha256:c543d8b0662a9915c913b7e10ade33410dd158ac9c48def3542d6b1be2cb1e3c",
        "p0150533_20050226.nc": "sha256:c3dc1967a150fe10e7e4861e7d1ec05e67fbde860d1cf1a8d8ce4346e541687e",
        "p0150154_20041024.nc": "sha256:8918624d1c75644ffe5cd587cea640ca6103be1cbc195da3271e006e313296cf",
        "p0150403_20050110.nc": "sha256:c149aebd39f27282e9447575a10799865181e2b61c25e35c53fad3f65fa9150e",
        "p0150385_20050103.nc": "sha256:1de02e862c8163c8022ba9ab00f4e538ceb51ece4cb5c553020871602f41935b",
        "p0150511_20050217.nc": "sha256:cf8b07cde5eefcb11cee1732e042b38ee5da5d2efd8caa18d847400b9234943d",
        "p0150246_20041113.nc": "sha256:85bcf3d96ebd31cda63d8a7005ced69deaa5144a9b22da7f46af4846478a996d",
        "p0150580_20050316.nc": "sha256:b4eeb996cde7a8c729832774337abc18aa665c277d4eca6756cb6c29d8910607",
        "p0150090_20041011.nc": "sha256:dcfcf9e8bce5cb14d5df3df8eee448cc0ef06f8dd9a4c36dfc7040a46e6b762e",
        "p0150130_20041019.nc": "sha256:5b26b3532c2e14708dfd8a57e1ff76a2e71d0c4117d719b8939fc96044c3f86e",
        "p0150103_20041014.nc": "sha256:799ae5c8e5c6be17c100315c4fb7945b24d7e016c4fa3710cc044354f20d1e38",
        "p0150326_20041212.nc": "sha256:f42820c4dcf99adfb44dfeaee8fbdca7b369f47b441ec1fa1e5cec3436149264",
        "p0150571_20050313.nc": "sha256:9d5625578b0c33ad09d26053eec895844adf13eee432b2ab6267c06fd8565343",
        "p0150051_20041002.nc": "sha256:097e0bfb9cb801fb0d17e940c43acaa7a9f4aa0f7fe3fe4950b510d23fd5530c",
        "p0150073_20041007.nc": "sha256:43741e24438ae75b8400877323fa503b69fa33d9ec4fda5376de94084c37995a",
        "p0150187_20041101.nc": "sha256:27f4ea9c093b70d8aed203904eef9b5d70ff2e8d67cc93d71aaed89d14f248c9",
        "p0150013_20040925.nc": "sha256:9d1334efb669ae7b480e38d22c68cd276638c7d6eaf451f3f61fe369d9f18545",
        "p0150261_20041117.nc": "sha256:a9fbd264a5ddc6aa9ad5f3ca61b547ba70b99fc8a43fd2d36d99b138e62de22f",
        "p0150233_20041112.nc": "sha256:88447a275c4c9174c941b4d8b69e504098611f14f5b1c6e436ae87cae547d936",
        "p0150453_20050127.nc": "sha256:e8356139bf4b14c46a78002bbb6d8b9b0507d2fb2d6780810dec2abf90380c24",
        "p0150536_20050227.nc": "sha256:62f6ea9f037064ac87c7e0625f8c666c43937680efde066dda0212aeb503638d",
        "p0150351_20041221.nc": "sha256:645057be82f88ffa150d3adb36ef239e7a88e23fcf5c848dace2d81333a56282",
        "p0150203_20041104.nc": "sha256:1c0042c0781d61c6e1fa5c01c4de531e2f6b6063dd2b52a22b804098b0469590",
        "p0150040_20040929.nc": "sha256:29b5ed6be0158dc19ee8f1489777e11cf4a8c11a446d8c60acb991c1443704a2",
        "p0150218_20041107.nc": "sha256:7d9ba02a350bf34399c26e2f3698d52d00d770742ef1cbf0dc7809703706c99f",
        "p0150373_20041230.nc": "sha256:863d75737b84391c391aadad8626cb295c83b0c18827be7b83e4c554e94e8aaa",
        "p0150562_20050309.nc": "sha256:497104e5c16812e9e90a1513b30ea9c7b3427a9691900aa1aa41dc5947c35fba",
        "p0150143_20041022.nc": "sha256:19c646c9aa4cb906939d133c59243f0cb52f9b51b6712a4187ad5c26b23615fc",
        "p0150482_20050206.nc": "sha256:1c1af48058ceb54da4e3c15558dc45834367b738ee0f2dfe43c1baadd82e264c",
        "p0150334_20041215.nc": "sha256:3a19bbd250e96de18345d5e4ec948b38e2d9ce6ef0f22791505015997190c852",
        "p0150497_20050212.nc": "sha256:b06eb1dbd4a40565353fe6b6619d14a66040a08eca53a16226e43d674aff2a1b",
        "p0150512_20050218.nc": "sha256:6f321c41926aa6ff14fdf20866cbe53fa497898f8a659c8f70e8f3d48f0f6ca5",
        "p0150118_20041017.nc": "sha256:a331f20d8b32da3c736601d3f217db2c565d33a1c80effeced8a9ca0cb2e5f75",
        "p0150331_20041214.nc": "sha256:08ab6c7409db8b44bcbd9da576de96b451befe6b1bd000b8b1f0bc2ea9f4913d",
        "p0150225_20041109.nc": "sha256:9a7b2c752e1ab19972091575176e384d980904a7485b51df6c52e8cb76f65906",
        "p0150595_20050322.nc": "sha256:c19e0c596b09d3903a8327aad3350a30c6018b81f579851405152e8d5681f377",
        "p0150429_20050118.nc": "sha256:4462d29ce025dae6f70985e8a825d9c3085c0f72c654e9e206b5bc3218affb18",
        "p0150262_20041118.nc": "sha256:eec532e8fe8deff9f0269b444a9f43010655e33ef22b134d2c562e91a94cfe66",
        "p0150035_20040928.nc": "sha256:64263e36d18a8c26996ef90b3cb91899e2d47260d569d0662e0048c2de3db583",
        "p0150473_20050203.nc": "sha256:1f03f5b732ed9851fdac74358ada2f74e14b696d8b4bbd46773b54122930a1d7",
        "p0150003_20040924.nc": "sha256:cd840f9ec4b1fdf971c021952b30482845cc0545a3649ffcbf6c0a1faeaf496a",
        "p0150376_20041231.nc": "sha256:c9102bb9415869bbb21e7be271c28341a2ee494db00a171436b98e001173db1f",
        "p0150521_20050221.nc": "sha256:6c84d448b5b4ac7dff34c90202aa7f5fc68555b138f9e074fe219da350e772ed",
        "p0150418_20050113.nc": "sha256:f57744d820e0e0a459e356cf4be55fb96cd16d4df75b8494366d9b00f3437bcf",
        "p0150199_20041103.nc": "sha256:2d61c8c990a75a517571523094174574419bb6f4f12a4a6103e7196f141dab5c",
        "p0150146_20041023.nc": "sha256:cb8b43d3aec57e21f3e2386a8bb632c5ed780011d1508c55994a7aadabe394dc",
        "p0150306_20041205.nc": "sha256:fefb485ac1a77751a0a59a87222d24fa93f0c71c78a19fc5090eab9c3034fd6a",
        "p0150182_20041031.nc": "sha256:3d1ee844038f00f39bb5cd46871178e944a7762479fabf1c3188054f223bbf5f",
        "p0150586_20050318.nc": "sha256:3d1b43feff98e929e264c97e442ca1af22cf4fe52f401ea1a02a8cbcf87ce79b",
        "p0150285_20041126.nc": "sha256:9af7be43ede3618240c8dad0d5dbb2cb7945d1b55e67d9653e5e0d2748210c38",
        "p0150616_20050330.nc": "sha256:eea84e354e136c617c0cb66c9033ef2f6a9a114e31e6b67462e8dc4a9700844a",
        "p0150097_20041012.nc": "sha256:c0a26f6c8ea81c99c92e922c6638e5bd97c59c1489c99be1f2fb21c42770dbc4",
        "p0150426_20050116.nc": "sha256:e3c2e92304df73852b8abe39cafe433f548b922c8d20591cbc9f8c7fb6be73d9",
        "p0150158_20041025.nc": "sha256:50da33bd4951e2da340eef50934f24068b6e42f2d75b1dfd2afe80743226d878",
        "p0150541_20050301.nc": "sha256:debd275a430f7f5b531e901b877fa8e76ea2268624c90e9c58d7cbd27d5788c6",
        "p0150448_20050125.nc": "sha256:fe84982f728995fc31a582567522b987712c1f639e13fcae8e37f502de06cb80",
        "p0150274_20041122.nc": "sha256:e7d4c0768a50a4efd8e575653be74640a749abd48124c11ef43d4d99795221cd",
        "p0150228_20041110.nc": "sha256:6234089d54c54d10e7cb9c6bcd7d618b2449ed275e5bfbfefc2e4766108d29ce",
        "p0150161_20041026.nc": "sha256:e49de453f51239a8aef0f39ecc5be4c82cc77d19b2aee1f148adff7952166d02",
        "p0150455_20050128.nc": "sha256:78671a0dd52786ac7eef7153c8fed02b07eab279a4912b1653f8c0ef7ad11c68",
        "p0150006_20040924.nc": "sha256:131efc559ed2c13004a584497fefc87130cb992290bafa05c53e3a69234f00d0",
        "p0150251_20041114.nc": "sha256:9065d957d002481ebe5b29f4403e2385cd74793d91f479b958b984c965f74297",
        "p0150172_20041028.nc": "sha256:fe9a596fb5333097ed54c675f48bfb93317d910bc584dce4e37bba3672946f3d",
        "p0150023_20040926.nc": "sha256:bca1067602e494007be035bd8b7ff5f99d43aacd709bc7d020d5850aaa4501d8",
        "p0150254_20041115.nc": "sha256:d956c595af64c66e1bd8370830c479b65ddde1eec1b948438f7ebcffd2bd4ecf",
        "p0150434_20050120.nc": "sha256:728c89f39b9206bf46d9b101b4cdfb091b268a79d46338ef14cc781bdf69a712",
        "p0150026_20040927.nc": "sha256:cb261047435ec067a3bd309b4dd54b04363f1743db429aeddf1785e433fc5922",
        "p0150301_20041203.nc": "sha256:2a15f73a282e133fe43e06b6852056cc79729ccc758aa8820267d43935eabeed",
        "p0150164_20041027.nc": "sha256:1f1fd4a2723716964b3c7b3ee8029c46131f698e377ceed6a1897a1b95ebb472",
        "p0150551_20050305.nc": "sha256:76b17cd1c36753ddc81afdd4364560e2c01cccddb17996d4ba29e56e0d2bbf04",
        "p0150085_20041010.nc": "sha256:5ad02ad1b19fe2676aab070bb284961db2f856cad53b0a01ad9a484339c1280c",
        "p0150528_20050224.nc": "sha256:489c50bb261cc28c1ec563762a14f700e5954ba3b5fd0c6dcc91067b13bb1fb7",
        "p0150125_20041018.nc": "sha256:71682c486e63a650f9e0a8be71f3a35f94833f4bebd796734ee3b65473c5efdc",
        "p0150138_20041021.nc": "sha256:b2bc4df2ef005b3f0ca03927811de8bdb986a1c854150c96f31d2b61128b0926",
        "p0150353_20041222.nc": "sha256:7cf84bb9f5d62c29530d93ff4b255442fb006ddf98338a1233fc6d90ae6b6fbc",
        "p0150231_20041111.nc": "sha256:a49cddf22f89c8eb1de8fffbe068ad2f3c13bcb9ea9dccee58b134cc3179edca",
        "p0150603_20050325.nc": "sha256:ec55ff25151ee62911c793690b4bdd97b751a44cf4422f17a5cb7f648dafb893",
        "p0150324_20041211.nc": "sha256:a5535356d75715660830c856cd700bffde0d02d88be26e0c7ba4e3f8ca6620c2",
        "p0150488_20050208.nc": "sha256:35d93f8f9054703c6da16205f3911a4abb519933fbf7fbe7c148be0316feb19f",
        "p0150340_20041218.nc": "sha256:d770d74309eb69dc0d68d568116bbe9970e1674766b4af6e458e6c667f220cc6",
        "p0150430_20050118.nc": "sha256:52057fdb91b079add70a3e22367b7588cdbda74f389e4b467a9aa0550a938fef",
        "p0150608_20050327.nc": "sha256:7edef4c4b8acabd0df98f96e2d0853c9aa7239428d61f3ad6d5cffbb2465f7e1",
        "p0150311_20041206.nc": "sha256:fbcc4d3c5e82212ea357de3589ed80be0cd812441f37e14a7d6b46ef621ece65",
        "p0150321_20041210.nc": "sha256:e88d8e07fe0aa2db870a1be474605b2599e641408de73c66a4e9433909d4cb5f",
        "p0150058_20041003.nc": "sha256:30702821f5cb047831f03e2770e87a41f876c7beaf55a5a57d5904e8bfe85e45",
        "p0150548_20050304.nc": "sha256:c7ac41df40ed9ce9d152fd62b57991ea8bc85f93bb2e553c9dbec4692d182509",
        "p0150356_20041223.nc": "sha256:e4e62551af90ebc74c9365ee414818f4696c257e5a8cd2fd45e1c290748b73e1",
        "p0150531_20050225.nc": "sha256:41be459a416e4cb3c0da8443f9ea25ed99793b24190ef6181e4e737da0d8a3df",
        "p0150438_20050121.nc": "sha256:3988112662f2f848fd5ed5db3c0ac84060fb208f90dfa2bf6545b7a14c8c0172",
        "p0150395_20050107.nc": "sha256:2c2fa19ad3e22ad0706d8011703a0d42dd82c507c3e05c82b61dd8f2890c294e",
        "p0150539_20050228.nc": "sha256:4538d484ba72fc76492f5001cc6f880920f4e02cb3e99abb21bf45f38c842236",
        "p0150523_20050222.nc": "sha256:a9b95ea815f672d332af67a1aee64de2bfb04c0ce48bebc5a2bd48315ab2eba6",
        "p0150134_20041020.nc": "sha256:5bddcf91ddddcfcb0abc36ebf9183d9f5e280f4339aa0b41e2f64d4b8fcb1473",
        "p0150129_20041019.nc": "sha256:b85325916f20866ae58eb77af9571def373428eef38479a76f78e3a0a07b7b40",
        "p0150495_20050211.nc": "sha256:3edb22ecfbb41e65f2f7a0cdb4d0edf0c0817cc9dd8172762f5a08960c1bc8b8",
        "p0150336_20041216.nc": "sha256:ac5487f20d3e7632f2056a660aa3515bf1466eb27d7e74338e2ebaa80c259cc4",
        "p0150084_20041009.nc": "sha256:b9236132c9a022a085f2c0c58e21adb126c2be0438ba351c530b75a49e9141bf",
        "p0150046_20041001.nc": "sha256:afe74f77725451efc6b485c201c16167b733023a49ade29b3142dfe737498a1d",
        "p0150443_20050123.nc": "sha256:7d5ea5ecbf658b022088e6eda701db4c5a7bde390cec78472fe204217b93c899",
        "p0150459_20050129.nc": "sha256:e99e4dd199843d57acd1f4d0441b5fd43c7c00ecf65dce8e6342647ecd35d8a9",
        "p0150526_20050223.nc": "sha256:e7706dc1ddc9332d207f61816c94367c3d11745810bba9189c5623e180b603e3",
        "p0150348_20041221.nc": "sha256:7a572c94cf81051cc74fa6afcc14606ff2bcc69424cf756eedcbd23102b6ea36",
        "p0150044_20040930.nc": "sha256:2f1edd70c0836dcc47e629c7a87020a05c469be1973746c69e041726fa9b9b69",
        "p0150543_20050302.nc": "sha256:f4868e72b37abf50d699da1603e0be3b97c82dcf77e5f61adbcc932f462c06c1",
        "p0150559_20050308.nc": "sha256:cfc67aea8c78527873923ba4b7bc658fd3f263be6ebd755925a2fbaa1a7b3686",
        "p0150206_20041104.nc": "sha256:00f80649725f9d3d5ce3740a526f3c28e01e1efb4d83df86ddfd471976ffa463",
        "p0150466_20050131.nc": "sha256:3eddd2321dffd085e12e111198cad23ca74ffddb08aa18880402e74bbd94ad0c",
        "p0150101_20041013.nc": "sha256:9926488c3a4319fbcd231c788a986891274f4cbad0f3cce6b25ba6b02a1762a6",
        "p0150604_20050326.nc": "sha256:b4e18e65b2fe8e7daedd416660fc3452b0bd919413b764452bd4b01939c9ebe4",
        "p0150018_20040926.nc": "sha256:873ad8832529ff853c9453ede2c197eace7e990c1458c081604a4d2ecd953b22",
        "p0150054_20041002.nc": "sha256:7e52a271c6140bbd3a10f0902040999a586472410a18559b40a10631dd74a627",
        "p0150421_20050114.nc": "sha256:648e0e4624f8f0c178c73ad565f4c068127ae652e9fbe1de03c3c176a9e74d44",
        "p0150468_20050201.nc": "sha256:4c4272437245c1993f3464a6542b2180544e63529c2d5cd466a6a6d53cc28830",
        "p0150106_20041014.nc": "sha256:2e933b97577dc0dc14ae53a82adfc23af2fe8c0528f5ae17f4fb4d4717047692",
        "p0150387_20050104.nc": "sha256:bc60a5e1bb7583802e67219c0b292b5ce5f8a12680d2d989594b77e28e3731eb",
        "p0150243_20041113.nc": "sha256:37396a4019f74023ada7e6c471985b5f23e095d3e4f1dd80d825e1945d07abe9",
        "p0150406_20050110.nc": "sha256:532b2c36828d14a8e79c4a1b00c65b57efc85d7417aaa6780c966a7bdba706be",
        "p0150358_20041224.nc": "sha256:7b6b676aa3529b3522cd16cc9e20108dae4881cc5cf85b45f8bdbc99f82eeb47",
        "p0150546_20050303.nc": "sha256:04bfb3b97f3b6fa3df6b717fe778e0ff2b3f79b2aaf3b29e3f8d9c4e50cb0495",
        "p0150612_20050329.nc": "sha256:d2266fcf6b75d7cf43c017fd692a8435ef4c1ddd6db7345f99b6def8a98b1c44",
        "p0150576_20050315.nc": "sha256:93b740d4d8d511ba4d09cccfb52d6e61752a6ebd9557ec837b2796d7a4cca90d",
        "p0150463_20050130.nc": "sha256:c92167cab85dc64364f31f085122ccc2402e417168d3e54fb7afca48a52f8896",
        "p0150240_20041113.nc": "sha256:55cd3c15b96ebf535d29be6f0388ae2f2abb1ce19a37a9064309d5c5196905b2",
        "p0150152_20041024.nc": "sha256:0f71927c8cdc237c8d2f897f2c5d4668dcf5d264b9e5c2651f1943684197c556",
        "p0150450_20050126.nc": "sha256:c0d814897e3c4444b952e7c6280f6dc0ec6045f7ce7265e75528bd2b1d66f6a0",
        "p0150545_20050303.nc": "sha256:c3ba4d9d704558e015f9c67c79c61d0764c1c190ebead5a179d84529ba0b0294",
        "p0150098_20041012.nc": "sha256:5b23e7ff8960e42c3c6e74427869f3f154162c5a4a75b1e373651132b2ae5e1d",
        "p0150405_20050110.nc": "sha256:af8258d6484d34d44ff5661262b7178981c80b631a3a840efbfccc7706de3c38",
        "p0150070_20041006.nc": "sha256:cc01e27453783fdfc9b779e3bb5e046c02a16595aa0d0f5b9c071ca50d4de2b1",
        "p0150102_20041013.nc": "sha256:a2b62fba67124a39429e5e9c74ccb081f2d7211b8c510ce75019c5209cb2723e",
        "p0150015_20040925.nc": "sha256:f4a2cb86c8aab3658fdc2557f107c1233b61235878aa58c178d701681748900f",
        "p0150075_20041007.nc": "sha256:03835f1ccc3cc60db919d3c4f4a9face9704bcd1884b1fc80995a7bb542729ff",
        "p0150205_20041104.nc": "sha256:4778f26f5fedaa0cd4b06c11625ebbcbb1b448d39d5763362d9b1694f3cc4e84",
        "p0150465_20050131.nc": "sha256:56b203b07b56a355fd544473d377b25a5532f06e172408ae527f5bc13e32b852",
        "p0150157_20041025.nc": "sha256:fdba18dca6f543c8986f0cec66fbb31c5897740462b043a5b87b7c7b33bba35e",
        "p0150030_20040927.nc": "sha256:c7cfdb908f5f77cbc39fbd25ad9ce5f648916c7291b48c4c69be39b92052da64",
        "p0150269_20041120.nc": "sha256:e2cdbbdef7d68386bf4ccbbed61457e0dcda52419e15e17784fbbd87b9427901",
        "p0150235_20041112.nc": "sha256:bd7eb6042b8c332ae48f60d884fb00ff455d19b187fa6868f37a549ce3865d20",
        "p0150105_20041014.nc": "sha256:b41603cd47976afbbaae9aa8218a980cb3803db5a48ecd9d58d67a5d141fdd53",
        "p0150583_20050317.nc": "sha256:8fe95ea186d764e1737692afa72d5343edef14298da0d38618404d9dce1b5880",
        "p0150193_20041102.nc": "sha256:8b8d9fd055cb9b24092afbca4cae925d655c94c1dbf8418b4f3da75bc0006274",
        "p0150335_20041216.nc": "sha256:9d4b6d58cd97786c5c6efe02f7dc03aa97b916a1c351204570951373149cef9a",
        "p0150319_20041210.nc": "sha256:aca3f4e7533bd0bdf77bb3a116fc75ca77cffb73045662da5d347a56f84ff0c7",
        "p0150591_20050320.nc": "sha256:5c674a562da7908b636f0f5fcdbd86d0a7d94be49040ac51b5f485f8008d9839",
        "p0150393_20050106.nc": "sha256:5f565a0136198bd0553b21df1bf4028e78e4e3322257fe8b3933690ca39714f6",
        "p0150498_20050212.nc": "sha256:fe50799ba8ffd3a3e3bedeadf81a1e3f5621a1e5526100ac4ca4a4f365541a45",
        "p0150367_20041227.nc": "sha256:a461a9f2b3552101b771cfa68ecc0d5a7dd221e47b3ab47f66171dafe1038057",
        "p0150525_20050223.nc": "sha256:fceba2bd52a0346b6f020c6acea135dc7e70a037ea577f121b62966ac375ead7",
        "p0150294_20041130.nc": "sha256:d22b1760c9dd643fe7a12710c6897f310555b3fdd8bd29b6960f0b467be855a8",
        "p0150565_20050310.nc": "sha256:bb27d4814a19b68ba0e6dd1260c96d46fe4738c5630fcd668ad0914092cfd94b",
        "p0150009_20040925.nc": "sha256:5a768d3bbfe5fe540a1b4821ff1e2549a6009fac4d4fef8a49c72b1df314ad56",
        "p0150270_20041121.nc": "sha256:3786143c22215049dcd312d7f67be673e90f18903c1b0b83553a44f092bff84a",
        "p0150396_20050107.nc": "sha256:f673be4a597786af9406dcef423360b49b3afaae483a3fdc079d21851944a09c",
        "p0150362_20041226.nc": "sha256:79f9d0835f9624ffc75d79644f6a2daf0ae26631521f0272bfadb484b57d02c7",
        "p0150314_20041208.nc": "sha256:129a26700cf4570e173b448c460f8f407c63705db34df8043781cb876a667b5b",
        "p0150493_20050210.nc": "sha256:43c4948b0187cd3b4fee9f710ce573ab58ac8c5563ec8a23a3c46b6fcfdefa22",
        "p0150417_20050113.nc": "sha256:1af426f48882b5d132018fec615ba25da94c3752047568399c171e7840670e4f",
        "p0150196_20041103.nc": "sha256:5668cd0ec3c463edeb3def39a2da135a3f1e0df733e462d4a3930e936dfcae38",
        "p0150149_20041023.nc": "sha256:d641258953f204585af11d4539f272fc22f722b18c1dfaf9ce78615eb420ab58",
        "p0150239_20041113.nc": "sha256:ddfeddf3151a9aac6bd5e66519524637536a02e27f588b40ef2c875d375cd102",
        "p0150209_20041105.nc": "sha256:6abda195eccccc40f3aaa1799b4fc01407120caebd9a6b69ea790f13253c71fa",
        "p0150109_20041015.nc": "sha256:51393fa0b56d4188bd00e937b2ea7db77a752891c1d7fa4759333daa640242aa",
        "p0150355_20041223.nc": "sha256:9962e181cf1c8e0b1973d097699aea724ea92958dd26eb59281994dfede9e852",
        "p0150249_20041113.nc": "sha256:daf29ee137f61e93c012230353bb47148bb37a0fe92759f0317b7f55bec2f7ae",
        "p0150232_20041111.nc": "sha256:7c40fb9983bb3ddd6dd3e9dfb8314ef8fd20293605452fa2a0e8749293a48e18",
        "p0150409_20050111.nc": "sha256:120d5717a9570ec95730a096e051bc2c9e6b5c203954af711652c0e618701967",
        "p0150188_20041101.nc": "sha256:0eac99ed4a553c77a6b38f9aba672780c7d27bbcf3a8e975670f0df8ad34bfd7",
        "p0150470_20050202.nc": "sha256:9ffe91e6f5a3e7e364085649a59bd61fb0dd45f129909bb8995f413d322006b6",
        "p0150167_20041027.nc": "sha256:67662eea56534bf935f47440fa7a2935836d77b24aa2f6fc8cc93d133e9b1918",
        "p0150507_20050216.nc": "sha256:8173e2d28752b783b0ed65af012981947d876264425722716246ce2ab604026a",
        "p0150302_20041203.nc": "sha256:2ef52088c3c5cefb0b58492d59fbaada0ac572b410fefeeabce2cc323fcbc242",
        "p0150318_20041209.nc": "sha256:54e2feb4fb92a4a3e540b7acf8cf5cb971b5dbd60aefa2ca304375e8d2e6d650",
        "p0150332_20041215.nc": "sha256:8550c3451c6bdb38787ff9fadcfb8164d0890260050a83156f361297e062c237",
        "p0150025_20040927.nc": "sha256:00eee8ac84ec58d601a4c68dea94b487746a12579b2fa7b81555879f558205b8",
        "p0150174_20041029.nc": "sha256:b4d7cafc1f094262c15299ed7afda81a793f9b6daf52d500c6645d662eef1684",
        "p0150477_20050205.nc": "sha256:50ea7b45702749df68288824b0848c4855ec190966049666db0aae6594133d81",
        "p0150286_20041127.nc": "sha256:2762f161ca34ac7895f154468df6f2107a3249772d8386e6253f248677910607",
        "p0150126_20041018.nc": "sha256:4fa98cfc56247d4bbdabb33e7f4a28da64aad7529e0ac8bcf8dc9ffa66ee55cb",
        "p0150086_20041010.nc": "sha256:f9fcd4ac30b26294fe4569974253e477d00c2c1fe33f2f1d64cb5442715a63b4",
        "p0150145_20041022.nc": "sha256:aea725cbf6e356d74660ef579f2b5a6d0b857677c4c9b1fd64488377cceb1959",
        "p0150181_20041030.nc": "sha256:ea7068bf878ee6cd4ec59635a27939f94f8ecb06d278ad2e23a1d8c93d678364",
        "p0150305_20041204.nc": "sha256:04c03e47ee9db42efed8a42239fd5f6981508c135c6fe70bb5428381658e7f88",
        "p0150552_20050305.nc": "sha256:88d67e9622102798b7f9bf55f3a6e9b00d7e66ca92e5d82f0948b3acc482a9ef",
        "p0150290_20041128.nc": "sha256:76a5b5871ae27e52a8f0dfafe73135f7018326e8cd00b393e49945e4bcdd8357",
        "p0150184_20041031.nc": "sha256:6c8425d34417a871a89ac4b7600ebf4e90c22a353d2dc1364c80799e77bc5184",
        "p0150296_20041201.nc": "sha256:4b643d924e619b85783b35962983a5f4082bb98cae8f82d5c14268f4aa4a0f3d",
        "p0150283_20041126.nc": "sha256:1d782e81288792be38177472d37e7fa0af0357b66a0cee6eb0b364e6cfe6a6dd",
        "p0150339_20041217.nc": "sha256:b53d02610d4ba99f74e47ef307550a1c29ea6c02fe26d14996fbee3be117f7df",
        "p0150347_20041220.nc": "sha256:ee97109e618fcc6e1c47bcafbc751050b75c1986e86bc454a24d891a71992a4f",
        "p0150264_20041118.nc": "sha256:af747d80c2fb50140d132e709a29d8642089f11fedd5c09c700daa9766c873e8",
        "p0150419_20050114.nc": "sha256:cc0ee29fc79958a15122189571a7765788ac60c9ce2a46fe804315a3738d3cf0",
        "p0150076_20041008.nc": "sha256:8953c59733a57e70c6c2597f0c6e6318e4fa5414900cba00c3d0acc4ef02deda",
        "p0150252_20041114.nc": "sha256:ad0a8f22291de98bf3db7c757ca16515b06d8cb0f97b5c981fbb22ce9a8d8c12",
        "p0150020_20040926.nc": "sha256:2d0b4a8e564b88c7fe8f831bce1ec02857d3a8b6f5e4f27d735aff59f6d328ec",
        "p0150171_20041028.nc": "sha256:6c49b6eef817173417aa33679568f030c5fb9e0aeefd63e5fc68059d03fbb1d3",
        "p0150005_20040924.nc": "sha256:9bad2e2016c1255f4ff3bc48c516366dc828e7c67f352bb0453468c88da5fcde",
        "p0150162_20041026.nc": "sha256:86a7afc29077a9fba808e30bd0b4fe53020fa3481d791d92b624bd716f0f81f3",
        "p0150033_20040928.nc": "sha256:e5fcbfee2b839b5cfc9b335d9c3413582f304a9411dd722bbddac6b7b7f51a7c",
        "p0150456_20050128.nc": "sha256:485d6059a465bedb72a9668df642f2205dda15041c09ee9e57899a3f9a7b6c72",
        "p0150322_20041211.nc": "sha256:85b617fd147798ed34f54dc651b41eafa5336575897b5a6a38b4abaff81dc2d1",
        "p0150469_20050202.nc": "sha256:5cb82d521ab97511e7c06638eefdf150570b5535e9699acc10f347aee0feaa26",
        "p0150312_20041207.nc": "sha256:421140fa947211cdc2d53741cd450d2a50c6a5810930b9b45de24b82e3ecb9cf",
        "p0150433_20050119.nc": "sha256:372446622b9527688e0f18811b6907192117fdc122ab214d6d7d1d311fc2b33e",
        "p0150379_20050101.nc": "sha256:c65db83fddaecbabd6d4a5d1dbfcce4ee0a01f534a7f1cbac766c4393d234d54",
        "p0150467_20050201.nc": "sha256:fa51113a6366987cb7997fb38570d7d8f6728bea0e956bf37382ddc08f482575",
        "p0150017_20040926.nc": "sha256:012f785cf0306f394d59e29b3c84a104d3687f1e1a6489e30373f43acb32079d",
        "p0150401_20050109.nc": "sha256:2444d3f082828844ff903b749c05d8fe14dfed4e0e47a5686a9fc2546e337b4d",
        "p0150329_20041213.nc": "sha256:9eb8b0a5d3c890439eeba0c3812a4691ed9aee2cc8456f6d037481c8e8d1d059",
        "p0150600_20050324.nc": "sha256:2c5e6e697745ae1016cb1d4f49627a31c638cddb4e9fc4bb7faaa3c6492da9eb",
        "p0150289_20041128.nc": "sha256:540deb64ed4de2833c69f939a4f2106096f64f9191e30e3c83076fd727e385b5",
        "p0150388_20050104.nc": "sha256:3041640b756828f977d7d92dc0e63af7c85d35ff5f443e2be5b494af79d1920b",
        "p0150615_20050330.nc": "sha256:1ee7507225cff0ce4d2c0aba680c285c246cc4bdd1c34b1b3d9e8c7dab7fbbce",
        "p0150343_20041219.nc": "sha256:b79319107800898ff65dde6fb6d960dc44d8c193298d753388811f273d6619cb",
        "p0150059_20041004.nc": "sha256:844c4e152fde964b1b88e3802d8b381756418055c2d37b51bc478754f5b6df4d",
        "p0150425_20050116.nc": "sha256:1982822836dea221f9522995f44c855eb64ba9b7b55abbdb1c8b39d52b506015",
        "p0150357_20041224.nc": "sha256:a49591b98fb6d722a8c109eb591d587113b5b6cdc31879184a675a77d29449cf",
        "p0150094_20041012.nc": "sha256:2efba5c399044b4901bff83cf1c8c182c7c1621d8a40b9090a6f780e0fbfe6d3",
        "p0150036_20040928.nc": "sha256:52797f4ff7abe424723d6764ea2ff7e1d88dec1413696291af4d4fa49d8fb301",
        "p0150484_20050207.nc": "sha256:65d077d5caa7e27a611cbe38bd237f606c33838a6b64db2eae588a3f2aeb58f3",
        "p0150596_20050322.nc": "sha256:696e52965bc21ff898b3e206649ea4bfff76cf88a8ba5eae3db9d72de5b786d6",
        "p0150210_20041105.nc": "sha256:c70f17213ed976ab7cf7406242fb7f569254fd57b44fd4074d5e0a042213dd50",
        "p0150226_20041109.nc": "sha256:eecf1d6fc0aaa81bf8a3166be54b6071a0122bd866e6fd14e4af10ce26486801",
        "p0150514_20050219.nc": "sha256:b1f09772e755fe61bbc7f190ae05780dbd98dc90cd7c1098d6a7ac366453463e",
        "p0150437_20050121.nc": "sha256:ea18c5d0e6dc2e003db4e036a9a27f62c1f66f51babdeaa162b94f6ca0ad3eb0",
        "p0150110_20041015.nc": "sha256:93efa8833be4db871aaafcf1cf2281d7d5c3af60cf5fe87feb0957a4ff278553",
        "p0150360_20041225.nc": "sha256:772443cc6d54c94cd39e999bb058ccd140f0c5e00dda7acc93b83cad0d0d5ac4",
        "p0150585_20050318.nc": "sha256:c204993cae2f6918acbabebbaecf5f606107a33b34044ebdff9868401d45e321",
        "p0150259_20041117.nc": "sha256:3397ef0bf47f810436e3def533e3660784f12c973c38d7081e8102021464c343",
        "p0150375_20041231.nc": "sha256:bd520f38719c6af72dfe9d1f2a307b3116a5bc491b41bf44e830bca9df764965",
        "p0150250_20041113.nc": "sha256:8df7b50de646b8ca0d7a5205fac0da9e271ec135f62552cf3f7a466eed08d412",
        "p0150561_20050309.nc": "sha256:ea40da0e634aa58b7d180fe4c5968229da29cbb5ce13ade9684a839adf0a3906",
        "p0150179_20041030.nc": "sha256:2d441a1fbc2284463f6f12933a7b7b51b8d8f499a2d523a70f4e755f951c0f67",
        "p0150123_20041018.nc": "sha256:e49578f58cf483d95a574c3d5a8873c701ce48e3486a8689eeef2a1496d2dd3f",
        "p0150277_20041123.nc": "sha256:76becaf723a7ffeb1be8d9604fe6dd860d6037f25f80d9d7462437a5acea7b11",
        "p0150223_20041108.nc": "sha256:92023c63312250c47d0763fdb2d1553be5965c7ce262ba86a1eb483abd44b7d9",
        "p0150049_20041001.nc": "sha256:53d879535318025c8a1ce03254e99da6e339ddb0bf05ec769523d77b0ea363e7",
        "p0150481_20050206.nc": "sha256:79700ccade2651bdfb5b2131b949dce2850ed19a031c9cc62e05f50bb9587429",
        "p0150410_20050111.nc": "sha256:41ec5da108ce2832aec1e5a6697b72e845fdd790b6a1e1638279d867b40ec71d",
        "p0150572_20050313.nc": "sha256:000cd25e17e6b525b6368d1b674cf5ad226cda1e2f73d688c8f6db3da67d1878",
        "p0150052_20041002.nc": "sha256:29d9b6a0cd8080a205ebc605452c295e220d074c305ef23de6bf3f4492216514",
        "p0150325_20041212.nc": "sha256:fcc2a735505898ed4eb3b8129eb2bae288b7cc8b58a52c571417375392cd4257",
        "p0150611_20050328.nc": "sha256:2ca4615f9988652c8bbe6b05f5ca3fee1114a356a745e6ffede374837971e339",
        "p0150519_20050221.nc": "sha256:dac81a580d8d5cb3e7786e06517b364797df2fc5892cc1c601c38b12d06d1e37",
        "p0150575_20050314.nc": "sha256:a1de84bc85b080372d70062f1a9a68cf35e152f3a77e59a6143d2c1731cb6126",
        "p0150487_20050208.nc": "sha256:07ec12e6aae83e60e18e95ee1d0873a8545c9face3660797e4d8841622a3e8cc",
        "p0150535_20050227.nc": "sha256:645d64cff1fa6abb7411a336bcaac34cbcbf9e96bd305e88a5e65a1c82f94bc2",
        "p0150010_20040925.nc": "sha256:de407658865197d61cde01b84ee1cc9d27121fe52de017f7c02b5624b569951a",
        "p0150383_20050102.nc": "sha256:96270041c9e703e7f4f0272409fb8bb90932dbd7c940de9acd1add74ede0115c",
        "p0150399_20050108.nc": "sha256:792459354ca47be14a48289afe802a086b74b1c4d9f36248a422688ad00651d4",
        "p0150607_20050327.nc": "sha256:e76142a03dcdcd438470896fc6ca2d7bbaa1a91b3b10b7717e9c2cf782f2c58c",
        "p0150368_20041228.nc": "sha256:7f0384530279eadb5b2077640a286482c63aaa073e88fef3481859fc69115bb4",
        "p0150220_20041107.nc": "sha256:9b3b9cc3dfe00b97ae93582b7592cdad1be3b67c1b68f1d6db678d20dd79cb1b",
        "p0150614_20050329.nc": "sha256:f209b6e90f9eda6355de66c304c37bd550bf92fdcf769445285787b79fbcf9f6",
        "p0150150_20041023.nc": "sha256:5b16d54e83cfa85e1b3f157d5a640dbcab7abd3fa3dcd5792223a7ad3b1cdc11",
        "p0150057_20041003.nc": "sha256:ce87a3688759a7f6c056fb19979447753c5bdf7f0cc0c2614003daad0412292a",
        "p0150422_20050115.nc": "sha256:c43aa34630f8b5de9454480b7dc709ca015b2350976f16a5953bc76e71a27091",
        "p0150093_20041011.nc": "sha256:6fc5b4dce2459527519cfd1424bf09729f3df79279e0396b76dd94ddb031bfd7",
        "p0150245_20041113.nc": "sha256:1c986cbae597090b01d12a6e7e1d2a32c269afe85f243f3fc704c83f9fe52783",
        "p0150120_20041017.nc": "sha256:25fdb39dbb4b735bbce980052aeed041779a371ed5ca840492bd940ca6da7f80",
        "p0150067_20041005.nc": "sha256:8ef6c9ed7cc0a1aa87c008582bf1fed1d9c20e38eea297a6c857d1efc665a84e",
        "p0150447_20050125.nc": "sha256:4c332d5f93f385d226742ce43e5c60640c1fa1f2aac9a7696e653eec96caa561",
        "p0150132_20041020.nc": "sha256:8ce04ac94e2f0496991469903ae6baa0cce7f193c094d47409f01a21ae96793e",
        "p0150217_20041106.nc": "sha256:44d54f754b47afa0e1a98ff8b00bc4cfec2ffd2fc49f0ccce2c2f1555c5bc5ba",
        "p0150281_20041125.nc": "sha256:43ff2d08a27ca2c736be037b355552570dc35a7a118f212d415c017ffee10502",
        "p0150117_20041016.nc": "sha256:9e11cf5fddf10bfff034442b364bd54383991aca13526e5454cfc2c674955d3c",
        "p0150440_20050122.nc": "sha256:4aef11214ed8f8940ce2456b84309d02b9ac4ebee33c691de1f3149cabee590c",
        "p0150069_20041006.nc": "sha256:a88cfb14c441bd7b4841a0f8be463b087e48609d1c56985ff177129f71199af5",
        "p0150555_20050307.nc": "sha256:5715831b9332a9eeeb39460165bab3adb31b15c62cf06038827447ef4a5554ad",
        "p0150371_20041229.nc": "sha256:d933ff6d60d8d28da0363f697b69a9d2219ea08d161b87b8613a61e1e614f401",
        "p0150279_20041124.nc": "sha256:a572057f4c409631e2b744b078a05d647f72ad75458486588d635d3cee601d73",
        "p0150082_20041009.nc": "sha256:6a3e1c6acab6c1a3e8482dfd404aec53c141d11a92fe3bb60887b1d1e90b5dcd",
        "p0150029_20040927.nc": "sha256:31600f51dc224e0aae5124128239e52dfe279c8a8daf78fc308b857362fabd5e",
        "p0150042_20040930.nc": "sha256:38b7a40c336c09845c80fa38b9f0abac17e6c7db47cc9197bd084a8e47227bb2",
        "p0150527_20050224.nc": "sha256:5385c405c913d21af0665ea63b53252a8ec77ee2f05e620937c997192f8f68d1",
        "p0150137_20041021.nc": "sha256:33d5effd859b59f55a062aacd1c51d7a3a12652b457138b576d469b4727b3d13",
        "p0150062_20041004.nc": "sha256:b2d33aa74bf9820c56fa87e885c55656ebfcf95e4c9ff81719eea2cca069a190",
        "p0150505_20050215.nc": "sha256:ee17adc0f68be25cc4c315fdf3df6b8a8f63c8295df170c3183521e49462a70d",
        "p0150107_20041014.nc": "sha256:db4b73367aad8dd860915f08da1a8406f946febfe55b6b495ead64190ba7bc92",
        "p0150200_20041103.nc": "sha256:20c5e20325b58a509f6a74e4e583bc0998de39362d4091e1e7bccb8e54e7c544",
        "p0150420_20050114.nc": "sha256:6570b66b1e53bf3e30a7ec4cd7c63d67678534616b44b8349f0942785ba02c04",
        "p0150019_20040926.nc": "sha256:95c6e0fa9e884fdd09e4a34209d1bf66925fd2355a6e8ceab478e7f8c9a11a94",
        "p0150581_20050317.nc": "sha256:9f4f20e726f9bfb9bec4511004f9117587f8f97bb900ea28c2f4566384b8da65",
        "p0150605_20050326.nc": "sha256:b7897bbf9562a406f7bbc607fe56e251e84af815a0ccc66b3fd0c16d551c5e5d",
        "p0150100_20041013.nc": "sha256:34087bad7e04c1237da59aba4ae420d982ed6ae9df427801d2bf626b7c74103c",
        "p0150542_20050302.nc": "sha256:5b8436567a34ab71e507ef9591a5fa04427d7538896b64887e9d51c72860fb1a",
        "p0150558_20050308.nc": "sha256:4483179c5e89dc2f7add6db0c4b64d9b35ed9438d5048f597dafbe4b3ab12a49",
        "p0150577_20050315.nc": "sha256:850c629929a52d22a055feafc40c18694d627cbd17ac4f48bf4229f3b5d7eff9",
        "p0150462_20050130.nc": "sha256:fcad1af0c914b5ec5b2d890d351850f5fabf6e1ae2826f87802a8863cbd1f239",
        "p0150613_20050329.nc": "sha256:93bd0211ea221d43d8168b74b5e4ff3fca536beee744a807de467204f8a5475c",
        "p0150547_20050303.nc": "sha256:edfba535c0358262aa36f5b36471a482fa11ed5574a2bde070856448f3f6293b",
        "p0150452_20050126.nc": "sha256:b8b3ca4c9cef4816a7b4c3f276c059ef14dab28f9116bf52980eea80ac58133c",
        "p0150359_20041224.nc": "sha256:7a807209a2534eddb5fdb4699b644a9d8fb767e9bde21991682dde51b7148f68",
        "p0150407_20050110.nc": "sha256:a484bfcc1b170eaabf8934129b240bc62e0f25131de138f2907f713f307c7b01",
        "p0150570_20050312.nc": "sha256:2b39ddf3397c9ca0947f120e49f4746199884f5cc3080c44b45589cc70e2ec98",
        "p0150327_20041213.nc": "sha256:cd41b7d325a32b53bb287d67d4cc51445ee4a85e68d56ad335675b0701796335",
        "p0150242_20041113.nc": "sha256:6656db4999e0c40c73e33805d69e6651b95b5e93b9e5c732a043a09700179ee0",
        "p0150579_20050316.nc": "sha256:2e22e51d2771d361e53f7bd19687c24a3d061444f2b28c4819f1651f8ea57a7c",
        "p0150386_20050104.nc": "sha256:23bd533ad75a7456938ba0ab16a0b4da35b5fa56725180624c6e0393e4ee8274",
        "p0150491_20050210.nc": "sha256:fc6a04b2fc51bfbe90c50e2ced653fbd8246fc465a730faa9558395e48b7bc11",
        "p0150128_20041019.nc": "sha256:48db7fd4faddea9b23d97fae07b922511c12aded6b1d83368ba6a18ba42c23ee",
        "p0150135_20041020.nc": "sha256:d7e8ddfb826429fa2fd6496346630a22a50e4832ae7a8b271caffbec7c4a3dde",
        "p0150509_20050217.nc": "sha256:2dae84a703c0d31b6e77347dccd2b0869d9ae8c89dea8f8616c7a1d54e554add",
        "p0150538_20050228.nc": "sha256:3cfba6402e55140b7126e5d447311f8d5b1111ae8d5360c6f1d317eded35a7de",
        "p0150522_20050222.nc": "sha256:07834ec50243acd823906fcc1819afb9a7e1011262e97f5f53e7224df5f6f905",
        "p0150394_20050107.nc": "sha256:f0dfd2baa2be0c9758cef0f1f25e858f85848fef73e7550be9e5bcb22e7d2b10",
        "p0150439_20050121.nc": "sha256:4402d7a796850e8408c6d0f9a403e6f919ae9a2cc573b7abd96414241f49534b",
        "p0150272_20041121.nc": "sha256:1b3f8ebf2d0b5709c7ad11cd74c10a3221fc826bb8122490414f5fba55338dbd",
        "p0150316_20041208.nc": "sha256:0e0099162a63a37d0600710ee8615fe7c15df47076e1c348a23b1948ad1bae0c",
        "p0150365_20041227.nc": "sha256:16998f7d4a7350cc5f2b39fb63bedb9ffff4dcd046d665d0335aa21fdbde0079",
        "p0150391_20050106.nc": "sha256:f086ad2b6743c1ffacc2e628abed56063867e2ca6c09e7fe03fb7367908d44cb",
        "p0150045_20040930.nc": "sha256:da17ae1d070a162bcb0016b3dfc49650f0662cb0db11f3df5344820e0c902f4b",
        "p0150349_20041221.nc": "sha256:aab8f366117e5ae2b1e8300eacca488f82064d9dccdf90b629ce88bc602a846b",
        "p0150442_20050123.nc": "sha256:3da7565cdb2f29c48b87ff9ddee91e238e68bc7c13621592d81615b03d0129b7",
        "p0150458_20050129.nc": "sha256:97a0603f2dd30a675c116388609b19ec717f6da087a1ef374e967aad24c2780d",
        "p0150047_20041001.nc": "sha256:efdd9266c5796f715c1deef5b0a12b19f25dd30253d303fef7cad6eb9ed740a3",
        "p0150140_20041021.nc": "sha256:a6bb3742711048a1d5fb32d3d18b665227aee49901b92ef09ff2df0682b16bd5",
        "p0150191_20041102.nc": "sha256:88c74e875e73c4d0c4b382bad60e2d64ba0d64a3242424cea836b918aaa5d720",
        "p0150177_20041030.nc": "sha256:89d5eec57331c3dfa4525aa84cc65629748402f3f87346b2b90e3e53e1b8d8b6",
        "p0150494_20050211.nc": "sha256:9d6a5f24be15b5e1c46dc5cdefb1d42160281645537a1ff90c3474e697aad5de",
        "p0150445_20050124.nc": "sha256:409419c98b82ba9788aad874cf6825cf4f1a8528f836bf5068ac0a799ac4ef18",
        "p0150341_20041218.nc": "sha256:76e80ea8b7f840271b0c4356b1a81056375c6aa9af3ba5fae613c4065a18977c",
        "p0150397_20050108.nc": "sha256:bb27ef4182ca2ab23a51af8b56fb51c8cc3207f72e2f7ec61bcb6ad681c77749",
        "p0150427_20050117.nc": "sha256:8abdc5ffaddd737bdcc74ca86e143476b55d13683e0a5009f1507d6b5b315dbd",
        "p0150602_20050325.nc": "sha256:369c0fa1aede1a5b917b10a4ed657f807968a93de534d5ec95cb3d42bd79384d",
        "p0150352_20041222.nc": "sha256:e534c69badaef98018ce1aad56807767a83456e89d43efa63abc021431ebf63c",
        "p0150617_20050331.nc": "sha256:32a78de8fdad8f9175deb877f6671f6fd1d1c6edba4fde33939e267864325610",
        "p0150530_20050225.nc": "sha256:7c68a37aaebfe848b660725631bfbfb4dfc221b6895864054457189db33a667d",
        "p0150549_20050304.nc": "sha256:f9efbe4f145844c6b6bee0017a4fd245c69104f0df69420836a7f4ce2ec0fd9f",
        "p0150320_20041210.nc": "sha256:41a053e16ceca4971aa33b3a74905e3c3665b54273d4e812f3b61c7448d208e2",
        "p0150310_20041206.nc": "sha256:378ae0f54b165e261e97dd32c556e824a0079da24419337718c99ef7a7f71dc7",
        "p0150344_20041219.nc": "sha256:cf8dcb129638d28da4bbc72a9df2e8b7725a51de4991752fa116497470b61acd",
        "p0150431_20050118.nc": "sha256:1c751bdd8e257383f7414094c779073026d963da453a9eda691634de76a1cdb7",
        "p0150345_20041220.nc": "sha256:a54e1b264054d5ce1bf33b0a19ee4c781264e61bc644311575737de428a724aa",
        "p0150490_20050209.nc": "sha256:beb9a6839b9ec1c8bf7b8df256e2ffa671689ca79a35fa752b16f85631baa44d",
        "p0150022_20040926.nc": "sha256:5917e4a92a0850190a084cc0e07a440d0aa4958f1d59ed05b1792d2bbfc4722b",
        "p0150007_20040924.nc": "sha256:172894460b55a6c54ead15897e85e267dcf8fd573e82f830ee13c3cc6a9683b6",
        "p0150483_20050207.nc": "sha256:2835de7d3916fa6a8f10a03494c9d50c116dec0a76e62cc9ed67d57978da64b6",
        "p0150160_20041026.nc": "sha256:53038e97371c8bd2106849c33328642ac4b2441c31862eb63ebd83f02f3197ac",
        "p0150229_20041110.nc": "sha256:90312e081c6c9b7f3ad09ef36a00ae4a8701327170fd115410712bba140ead4e",
        "p0150449_20050125.nc": "sha256:f5cad8ea5eec24f258ea8e6c5c01088053e552ecf7f8caab7169e841447f9d93",
        "p0150139_20041021.nc": "sha256:7e375178f42a651d954ea9746003c0b6a3a18460ddd5fa6d42d96f75f7d64ba0",
        "p0150124_20041018.nc": "sha256:a22ee11cc9c004a07137f0ad19821305c7e42bc4c15eeab78144987aef4fd675",
        "p0150587_20050319.nc": "sha256:8930881058682be2a746f3f922f790ab5a2aa258564ccab51bd6dd0db424971a",
        "p0150550_20050305.nc": "sha256:9be133115c45d65da2e18a8d4aa039b23d5dbbf8a51b3bf345346da4263ec1ee",
        "p0150165_20041027.nc": "sha256:c25a7c47f015b433a318ab828bd29d32c6e62f4fb797e737d644653d74164a89",
        "p0150176_20041029.nc": "sha256:63ccf5f0a60696911f6544d546653c96a9280e1be4b3d18dc6ccf745b712fe3c",
        "p0150435_20050120.nc": "sha256:35a4fe18d782228b4865915632f2fa104e8f3d74bd6fd52baa791da90fdab5f3",
        "p0150027_20040927.nc": "sha256:8d5517d116b9db7945b0ac69992b8b8864646d3dcd6573bab8bef2126f55b6c1",
        "p0150224_20041108.nc": "sha256:ca62f9ff15c4ba619beab3db9a55aa3d28956cdd6992ba9c32e41674c2fa257f",
        "p0150255_20041115.nc": "sha256:88fb922a9e0a876a9c412ee5bcaff21e00b2019629baae3c474f3d6269ea559c",
        "p0150489_20050209.nc": "sha256:c29f52cb69500ee87a59e529b2d3ed6421ae8e91a778f09cb4f4d35ae69a3013",
        "p0150517_20050220.nc": "sha256:aa70f8b4de3c6740d43c622064726e0b47c132b63773c13d78ca0e73da30c525",
        "p0150096_20041012.nc": "sha256:2c8208d4cc28f5a41e35ee88aca0f08465ad2c566748382e793af2f99a8c7bfb",
        "p0150230_20041110.nc": "sha256:cae2120d85a4a96d8eaabcceb11a32acd737785d8e7539db4d59271cc8341fdf",
        "p0150540_20050301.nc": "sha256:032f2dca66de3bd6c6407ab9dcbb5188399b9df75c5f69c31d77853933d859f2",
        "p0150267_20041120.nc": "sha256:c93a491742ff65ebba77e91c4964dc0dffa4c6435d684dde742248f2e4ed3790",
        "p0150159_20041025.nc": "sha256:24d565c6ed710193d3b7f584fa9bfa9bf0af110a8f8d87088e03cbcb8be0368a",
        "p0150266_20041119.nc": "sha256:18f5654c0681412b10d1ef657e21f88f9d8a9ba15dd279acd1e35c80d8624ca5",
        "p0150119_20041017.nc": "sha256:741bc9ca40f13a9d4b3bf0e6094d3143d98719203f8e35531b293814a9184884",
        "p0150513_20050218.nc": "sha256:c3bcd16944bac7ba34d43128b71e6872cecec2b5a78e522734b1e32f455ace32",
        "p0150173_20041029.nc": "sha256:c2489c88dbd1b20a2580f753c0fbfca6b67ebb223bba055b21657769614b6c89",
        "p0150496_20050212.nc": "sha256:95bd2bff68c2a8379f9766a4c90d594bc060de9c4050d01eebe816cb565cc83e",
        "p0150412_20050111.nc": "sha256:ded920141202abb7de36f1b0530788715d29ebcdf767bcea89d392d8adb3a592",
        "p0150142_20041022.nc": "sha256:9896190a66fe144dd80f6832e355ded23cdfc5d5818cbd6f38c12bbec683df38",
        "p0150292_20041129.nc": "sha256:b4bd9cc7a0084741bfa550259dc9c514cee2dcc9268a60a95bf88a7c401835bc",
        "p0150219_20041107.nc": "sha256:e3c253aa3a42cb3860ad8a56d98978b8916bafe36695d563dbe06ce904eeccf5",
        "p0150275_20041123.nc": "sha256:6d86653829dd04b68fec59ed3eecc7fad7134ead4599bc08de7df3730e1ece73",
        "p0150475_20050204.nc": "sha256:e227628883d6aba7caff25cdb8a21c1d7107fd925b1636e1e1e1a5399a211c8a",
        "p0150284_20041126.nc": "sha256:a724564552eca810dd3e596b76f5cd246e48884af90dcae6c044aad379bd8173",
        "p0150112_20041015.nc": "sha256:cb786ca197fb93434135955710103cf305901b992dab76fe6ab8a7774999fa30",
        "p0150529_20050225.nc": "sha256:0e45d366af5f3903aa7a46b4727681e55aa628d759e00729306aeff335b69564",
        "p0150198_20041103.nc": "sha256:f164eb3a38bd6eb54d0eca6eab07404391453b3cdc24e7e94a3ee7becb555c10",
        "p0150147_20041023.nc": "sha256:e50d38779b434e883931067170ffd63f1470ea58a818bfbbd06623e71b1f2266",
        "p0150183_20041031.nc": "sha256:1eef33409099d57f482c5bb13266eeae8930f4722e888fe44cefd5a2d2dfad3c",
        "p0150307_20041205.nc": "sha256:65b35e26f1bfea9889bae0bf275778464032107533fcb0de5f67acf7771c1065",
        "p0150520_20050221.nc": "sha256:74334c064b8080bcb3e81551cc0937d228537af9f72b9e1277c51f7bb1500663",
        "p0150377_20041231.nc": "sha256:fc7cd0b8e0f00f17d6037f795dd91eea6c12162b7c3b74a168bfca049a21df50",
        "p0150309_20041206.nc": "sha256:a1cc8108454021d5cfef6887cead5446439d88d450d5074c24a067e13c38ad9f",
        "p0150002_20040924.nc": "sha256:99121b66c980487bfc93cf014739717f28be829b612f2fb9999d130389a4c46c",
        "p0150472_20050203.nc": "sha256:a10cb9fb94004838e67373f988199b14e8ae77307cbb19aac0e9e9787c689fe6",
        "p0150034_20040928.nc": "sha256:c74c0368dd255455f2ea1bb4454ded6b6fb7662651f93933ddc21a07d3d50553",
        "p0150263_20041118.nc": "sha256:1e8d8b132ba1fb2027599f88a636bc26a72682faa6d7d767f6970048fc0350db",
        "p0150212_20041105.nc": "sha256:35d1cc6c9224dbf7a95510b197446c341eda28544bcb62c73d9f1de5428c811c",
        "p0150300_20041202.nc": "sha256:77ce951f3ed39034ae6ac56e715d43670124cbdb1c9bfd9644f18829e0f0631a",
        "p0150594_20050322.nc": "sha256:5311b60abca2a1df90658201bf7bbd16eafb8e5b1340e1505266a9a4c1de3716",
        "p0150516_20050219.nc": "sha256:875f8901d1ad85d63b6492a8c4ed8dd0b9bcd4a5eace34a8cf95c9524402c019",
        "p0150330_20041214.nc": "sha256:0b11c917cba0bdac2cd1d01e60a2987a6842e4908840472c3815c59f66b5ff49",
        "p0150091_20041011.nc": "sha256:8ce4c128bed2e8ac15632e5b9c75e477bff85a5b46f21864d756c907f9a0dece",
        "p0150055_20041003.nc": "sha256:136ff8a119797f2b7720367e8498d58a6fef36c7f9d5a4a4942f4e0c8f381db5",
        "p0150122_20041017.nc": "sha256:134e6906e3b72e5c99c9ebcd1fd4f833b61607dcfe83160fee98dffe9ca64220",
        "p0150247_20041113.nc": "sha256:2718049b23d3492c01086607157b53f376bffd0dc9c5c19f833a2a843a6c3d2f",
        "p0150510_20050217.nc": "sha256:68a74fc1bad470452679e71ef0cba117e6d4cca17aa33a1a39e1efb1c50317a9",
        "p0150402_20050110.nc": "sha256:a5b6e0afa8d94d7e8df96f0654170e00cac40ef01cc42561c07e41138b396e50",
        "p0150384_20050103.nc": "sha256:853293bfbdc432e8ae2087bc25e32df7f9b6c211027c2f89da24e75f4ff489d9",
        "p0150155_20041024.nc": "sha256:481187fe91428ac96a0e2004e76f792f3ab9be044ce87b53fc554cfb84c2f289",
        "p0150207_20041105.nc": "sha256:0ede22b9844444aab3bbffb50dbadec59caf299091ff667d7cf8e40f8a4248a9",
        "p0150532_20050226.nc": "sha256:a8b45a18befd7232d2ddf712ef9775d580b1758dd75bb7561a60fda265f52c25",
        "p0150237_20041113.nc": "sha256:637328c3fa58f7bbffc772e1b498fa0c71aeba07b40be9104170da6690ecdd29",
        "p0150350_20041221.nc": "sha256:b0ba51b776f1cc582ff9ca011cc8d982aff9c81bb13d02f3830bae03336067bb",
        "p0150202_20041104.nc": "sha256:76a51d2f6112c8fe824f50abf7f36f5bb3def239e8481bf3131c18199a3fa9ea",
        "p0150485_20050208.nc": "sha256:bc50fb2bc4ebb241d76dd159313c5cee568dccffabe7e3df244b67d1e5cfece3",
        "p0150260_20041117.nc": "sha256:88f414438b18f47b0b0f7521cb4748a0b805dbcc1d9375d38a5543089bdb2a84",
        "p0150186_20041101.nc": "sha256:de89603fc032f8d016a883930f57202bdcb6b42dcfd3b65d75397b078ff95db7",
        "p0150012_20040925.nc": "sha256:8d1b60a171a2d655020873ee326fe0557cbe44dbea6c23a8099a7ff26ba5ed6f",
        "p0150381_20050102.nc": "sha256:844a55919cf61575997817fcdc48cca15a5d8ea7265c2d884e0dac749676f648",
        "p0150072_20041007.nc": "sha256:f17f80f6c225db411b3d16f8b3d8acb4a13e46006331143da64d298815f329dd",
        "p0150050_20041002.nc": "sha256:beee165cd78b9617cea5e5862703c3f865e9ef66ffbc251b10fbc8d286ae5e15",
        "p0150257_20041116.nc": "sha256:b107e6969d2225803389eb442de52d37cf0a0f69c7b69198c9ea20887987b04a",
        "p0150479_20050205.nc": "sha256:6cdd85728bbf65cbda4e73530565e2030822821f494c1fe36ac56cced86b72df",
        "p0150415_20050112.nc": "sha256:2398dbcc93d0ca0c49a0811a2b2f51699c7e5a363d3d2f78b7ef8437395cbb99",
        "p0150060_20041004.nc": "sha256:e059537000ec649ebd0a3fc22871481f4d2bf9267ccf6f361a8972ca102e3709",
        "p0150088_20041010.nc": "sha256:a79e3efbcf6a6fc927d173e049c8f778f412c085f0fd60ab63002dd0452901f5",
        "p0150194_20041102.nc": "sha256:a511c75eabb60608298116ac7c028007717c34bcfbc1e94f97a42e55fa963777",
        "p0150038_20040929.nc": "sha256:fd68991e867b526ca39978419bb750de75660aaf878001cd05b45f81660f7caf",
        "p0150080_20041009.nc": "sha256:143f4648e73177753d0df6be227500a494e8775afc53627d11eef247f0eacd53",
        "p0150293_20041130.nc": "sha256:5ecbc5ac9410801112bc6d0a49893739cd6b709efc7e21052b1e5c8c8fe2f19b",
        "p0150598_20050323.nc": "sha256:baf3ecfa040dcf6a5e1690ab53b555f0227d155eee2f142ce2bb82b9a291406b",
        "p0150078_20041008.nc": "sha256:8e5843ebd6bf07ac1ece72f7df37944ca1b854124a4b3283e0e2dedca3105a1e",
        "p0150115_20041016.nc": "sha256:e464e2fa05ba018ea411c57e824afbc31d3ee8f351a5276730bf8a49354b9319",
        "p0150557_20050307.nc": "sha256:6244e16af28bd4d4e7248cc778c93045f7d83fbbfab9157e5f4638106aca0f0a",
        "p0150567_20050311.nc": "sha256:58363632169172ac3c0e08482b4ee4759715c36c19cc642de9261e67f1e815bc",
        "p0150065_20041005.nc": "sha256:875cd6c0754655755f0ca158712b0bf824f8732d28a87dc622baaea12e14e3b1",
        "p0150569_20050312.nc": "sha256:7098a165bbf229793b1c372faf60f3339f2833ab0ddf4b04c1bdc4d4aea13832",
        "p0150337_20041217.nc": "sha256:e9718428df5c65d342cb93a5f6bd49d4cbe4e2fb0cef7a6d6ddb4edca88ca18d",
        "p0150593_20050321.nc": "sha256:04598884d3bf05a99abc15f25a303a2653051ce9b8d926a1f06bbd5f9cc35f59",
        "p0150298_20041201.nc": "sha256:3d079074b2d1fa0201aa6bb5bf4a40d4fe0081558e07587a5ac3f9a62fb9f180",
        "p0150215_20041106.nc": "sha256:c46f204b5509d45ec477609913489a7f34550add845bf31a98b9beae30ce6102",
        "p0150441_20050122.nc": "sha256:dc8f551f3cd25301b270246ad259bf8b5de06ca0da2c38552b36cb91be277239",
        "p0150068_20041006.nc": "sha256:db86a7c81fcaf33f6f101ecfcffed0acaabfaf6fa991a8a156500c18558f6526",
        "p0150524_20050222.nc": "sha256:540ba3e3a2da1ccf799f9d4596e0991ff3ce512637e12b42c1c83748f1765016",
        "p0150116_20041016.nc": "sha256:704d65dd13752cc47b5d8106d2b974bf9ce53834dfb319368ea0d27b4dacbcbd",
        "p0150280_20041125.nc": "sha256:b8c34c4c50359f00f1df4cd1bef30f5bf55ce1b016434d748174e7ef8e1a55ec",
        "p0150499_20050213.nc": "sha256:c9175fdf564f25a9eb6af5ffc1f972aa57f721db6586608d8a7c561b78e29b5b",
        "p0150216_20041106.nc": "sha256:edf4ae3bddd099b1000bb76ae4a670b7c4c3c37bde1cfea324db3c0707c7f3f6",
        "p0150133_20041020.nc": "sha256:fd2ecde24d033ce014203267fad6e4d5455800c49dd2cdd2a423ad1cd0a28d05",
        "p0150066_20041005.nc": "sha256:91fe58a095051215aa3d82561ae7a3d3848e197b6e08dd80bc043929e91de6be",
        "p0150136_20041021.nc": "sha256:0aa206bea629aa612e2251369cc471777009b7d61dd65c84a7f57414361d3c9f",
        "p0150588_20050319.nc": "sha256:13823a51abb45c4243a976cbbed2786d12743fec11573354ec3b822cee62574f",
        "p0150028_20040927.nc": "sha256:6d3601d089c5ab9053b6884d94feca1821d1ae6739621c4bf95ba1e9b75e0140",
        "p0150043_20040930.nc": "sha256:ef20d21b554022dace11c6c5afe26428816a62c467d70692eae3db6f2f0cd7ce",
        "p0150083_20041009.nc": "sha256:acdc5c81a071a1352ffb3a92fc8fa2e03fcb9d83e37449f1cb773ce1f92d1cb3",
        "p0150278_20041124.nc": "sha256:4cad2d49eafb657568639ae16c47192f10aaf2b158f4dd0b32b9a3f5c0008ece",
        "p0150444_20050123.nc": "sha256:1726acb3405bbc6b11fdd1d5f4c54a54c7fa6c2c2ac5d7acaeda9cd9871a4dd2",
        "p0150370_20041229.nc": "sha256:ec623cab7cb9a612a18da1461809ecd9a92bc72afa04427aef4802a81b26a23c",
        "p0150382_20050102.nc": "sha256:9aa909272e1290cf03e757ac59668909af76014b904d65c10f4f3470710b8f4e",
        "p0150398_20050108.nc": "sha256:c547fca477042623268e166c2bdc28808b8f7e7a2a28b39c53af5beea30638db",
        "p0150099_20041013.nc": "sha256:2a35ab993b8ba6954ab4e72ab5beea23fd5f3d389912ef5cd0826df54a6b85c5",
        "p0150428_20050117.nc": "sha256:f469222557a8bdf9ce5bef56534d72dfaf4b8916b10a99731f7ebff0677ee456",
        "p0150011_20040925.nc": "sha256:804ad8392b50d6555ec38ded84a4498b467bd2907393fbf224c3af83050d4390",
        "p0150544_20050302.nc": "sha256:49a6058673aa3c5f5ede0b1aac64016321060af6a17f4485e27b92572b8e825a",
        "p0150486_20050208.nc": "sha256:0cb1d0151efcd64f7173b1bf189161e4c70091839966806139d2a746d8f17567",
        "p0150574_20050314.nc": "sha256:a19ee6343aa99365d8747f66874b3301642282e512b205cc1eeb6e1ee764b393",
        "p0150201_20041104.nc": "sha256:46f524b735fca44cab6b1fa1429ebe21c311050ffaf3688780e942c85420bf79",
        "p0150610_20050328.nc": "sha256:36849728a735229ee438c9b3ced6af4dd2b9ab8a1e56d66c134d89578ab4304a",
        "p0150589_20050320.nc": "sha256:8422bfcc0459755350b245fe219b4a907b82ad1565d8585d2d6249145c3d6fbc",
        "p0150053_20041002.nc": "sha256:9b9232c837e4a65d0f2bd35d1fd37f77db5e5c92ced8a901afbb4c571026f104",
        "p0150573_20050313.nc": "sha256:0ee7e3d5d8cfced962530d17a0280d715ab3a12ca8a410cb8d838423d7581e58",
        "p0150121_20041017.nc": "sha256:42a3617bd953bf7191cc6863b5ebd63d1b8f273c9d8b416913ecb5df87ef5450",
        "p0150244_20041113.nc": "sha256:f37d030816d1bcb5a7d283b16e694c411d2c90d91b089e1470f0516d5bbd7482",
        "p0150056_20041003.nc": "sha256:23a702b490cdfb5be6fb9f7942aab390970186a33dc1738fbb6dac8d1de0e5d3",
        "p0150423_20050115.nc": "sha256:22e286c4440c4c6fb3bc96e8a28a6d7d06fd585da03e84e1f60d6ea2ebe7bc14",
        "p0150092_20041011.nc": "sha256:63e4597c416c23f2b24190a819db243488f548b10ec9f92c45377dcd7c44d64b",
        "p0150151_20041023.nc": "sha256:d2242858471ab9289f23fe20a7f4cdc64ce9a7fc749a5af33047d32fc37a8942",
        "p0150369_20041228.nc": "sha256:4afebfd891478fc7dc6034d0775ffb6142e89cad468048926372d81c0d46f654",
        "p0150221_20041107.nc": "sha256:5872eaff43de6e519e78e3c21277fd311afd6f71463681e1f4031778bcbc6346",
        "p0150127_20041019.nc": "sha256:842ac8436331343a5d1d2f0cdc3e33bd6d4d5f430c969ac58a7a78ca7768ab26",
        "p0150273_20041122.nc": "sha256:7dc01572f6a995f520d2c448ce13904cc2cd638931aeb8bec192109de6da7704",
        "p0150361_20041225.nc": "sha256:a0af203fa3597a71e28cc4cb8e3eafaec78e89520a9f17a3feb19b8230c5b69f",
        "p0150584_20050318.nc": "sha256:821ccd762d854f4f57f0dfa8c714f9e48180a08f69d9339cdcfe78a653d963af",
        "p0150476_20050204.nc": "sha256:2f24dfd89afecf5082e72ae91524e1b822b7faf9e3ec4d5dc2395a474e15ad0a",
        "p0150111_20041015.nc": "sha256:3e5d05dc7ab47a1562844aa05c36dd3f9cb62d883d3e4c7778cc2fde274cbbe4",
        "p0150024_20040926.nc": "sha256:ecbba0f4cacf75aedc1f5dc6ab89c6a720e85cde638004f4de78c3901a08c741",
        "p0150515_20050219.nc": "sha256:5747f0e087357d9a007dc819d7f5d22897b6fcbd77ddcfb9d930c68083c7ae7b",
        "p0150227_20041109.nc": "sha256:70d0cfbb989f45ed94799032a804988b28138ba96c718dd0669d95bbf7c0a6c2",
        "p0150211_20041105.nc": "sha256:1be522ab9038ae4a236022466d512ca728b77c8951db529f3105d75e07a22790",
        "p0150537_20050228.nc": "sha256:901b6a17fdca45b3f83ff1b0c6d42746557e17ca55c138e88c6ce9a413d36598",
        "p0150001_20040924.nc": "sha256:f40a41199b2adcf2b07e86a41ab278b4804e730fed26831d7a4696bc0b565763",
        "p0150411_20050111.nc": "sha256:e82589789febe6cdc37dea1f853d56eedb85d4955849a26187cb67638039872e",
        "p0150480_20050206.nc": "sha256:6e88dda5d896d5a942d2ea428bf1fcb600a098b41a4cd53eb90f1d83596f5e85",
        "p0150190_20041101.nc": "sha256:7aa603e4a9c0294c42fd3f97105470afed9a7a1e7a3a7707b5bcfd98181fbc08",
        "p0150048_20041001.nc": "sha256:b335c21a82135f89a86113671e1c373b2ce8222cc0800c3e020b90cce48a13ac",
        "p0150222_20041108.nc": "sha256:5f746907f094e14bd8fd2aa5b63063d572a30ac88d3ea8a764e66bc9244cb8ab",
        "p0150265_20041119.nc": "sha256:8f44f0d53c8a1b2847d0e87738a35d61027483b345a090a7ce9f66a7bebadada",
        "p0150276_20041123.nc": "sha256:d8f5dbc600f040e560e78b52256319b6d92c1077629465e6bf6903b988128160",
        "p0150178_20041030.nc": "sha256:9685f691d998de8c76aed81ab6630a7cc9898a84cf1aa95e47b8fdcecec75785",
        "p0150390_20050105.nc": "sha256:d37c316d8d8c8b5825dabd9d832d0847bf73a7dedfc24f673cb1b72efe0a756f",
        "p0150141_20041022.nc": "sha256:d35aa48287ee2a45d18fb878639304dc7267be9ca11b33d75633e7d6bb179bf1",
        "p0150291_20041129.nc": "sha256:4a4be3bc2359dc8c2eb147833de9ce5c335d400452ea74ce51908f06276a1d7a",
        "p0150016_20040926.nc": "sha256:e594ecc5e743348ccf98676f55da34b164d52c19085016f9163643f4db53dc53",
        "p0150354_20041222.nc": "sha256:8216b3892347eaf9c260660cd1cd6551959596ee96530d68de4a579068564b6f",
        "p0150108_20041014.nc": "sha256:99ac550983907a9681a1a3d0a9eab0219412ec137a0b601c7f722610733d48e7",
        "p0150378_20050101.nc": "sha256:911e8ae886857a75f2ec1ed1f937b69d7f9164df59339d235304332258a95106",
        "p0150432_20050119.nc": "sha256:ca38af142f1f30677c492bebb8fa2401f45542738a335a321fea88436574af41",
        "p0150313_20041207.nc": "sha256:bd78870e882d66773a54ec5f40801bee90ca7bf69bffafbabaab4705e56fa569",
        "p0150323_20041211.nc": "sha256:073f44053874a29dbbf8dace08c9bcd00bda934af1bf3265d64d40b87898251e",
        "p0150424_20050116.nc": "sha256:885d4f1dbe0282d5785b7188518f665e4423b8bce764d7730977549e2b201304",
        "p0150095_20041012.nc": "sha256:2286c8bd70441640cc8b35bc0f67391c2181ff03b2f5969213a57d55e062e961",
        "p0150408_20050110.nc": "sha256:5df9f6d7b85e4de4b297dd66db1813b0ae518d8263266d88272abbe644a1193b",
        "p0150578_20050315.nc": "sha256:5f75d7d548ba360236338d4108442eeeaf3ce19c57688f4752cd6a8659060f3b",
        "p0150169_20041028.nc": "sha256:30712dc51d9961f80d781b56bb91aab31300ad6744088e51a34f8fbe14f46f74",
        "p0150288_20041128.nc": "sha256:794ae918431cd6601a5fa7d01270298e7a4d25799a3992e50abdb59b750fcd38",
        "p0150601_20050324.nc": "sha256:c595cbc31698860a6647363682f4e75841cd5b06cc6d0631515d210486c3d516",
        "p0150328_20041213.nc": "sha256:2f5d4cf609dc46dd19ceb28e6e0ee047a44a3baabbb4c934b0463182a70afb5d",
        "p0150400_20050109.nc": "sha256:16a7b3640677cf354ea67a20c2fcc07209cd34096e637af1bf92b316e1e1ba07",
        "p0150374_20041230.nc": "sha256:b831897974c11c3730cae9d3a322f68057f4ad0cd0003763ad0fe1bb20fd9a88",
        "p0150144_20041022.nc": "sha256:a0ca1946419f85c6b35af81969b9ca5330304cdfef4c5bfe10bb622d1d9b0bce",
        "p0150304_20041204.nc": "sha256:1b1d4d616ad2e8856669eb7dad761a9f4ed97fb942c02832c63c17e0c2782d3c",
        "p0150180_20041030.nc": "sha256:8bf874b5cabfbea84e52b43e589a4b88a89845d88e22265da159fa24f1e8bf6e",
        "p0150087_20041010.nc": "sha256:bff27d954ac002d6747d1b152814e9e3c07d928ef452e8c3148405d9a9025ea2",
        "p0150258_20041116.nc": "sha256:79bf0a0ecbaa4dd828f717037065bca5d78911d6b25104df6bea3d03a8b5965d",
        "p0150287_20041127.nc": "sha256:1a65a44acc99f785bdd228d22772cfaa3c64b421776a3dd4b1474284be3c8f07",
        "p0150436_20050120.nc": "sha256:dc37481c060e2bac6807f0c5eb72f7f1ce34c23ba3d28b1e2d52f756485641dd",
        "p0150175_20041029.nc": "sha256:3f244b3404e99d917d6f537378edbd095230ca10efbe2cada1f9a1514e1a9114",
        "p0150333_20041215.nc": "sha256:e1066f72d005318fe0117b3287413b0dcbcb719153ce100d436d30d6ebe4dd7c",
        "p0150256_20041115.nc": "sha256:102dc856e7ffde2047426caa42e9b65a6f116f877e463c64343cba03e4b09bf4",
        "p0150303_20041203.nc": "sha256:bbe1be31631c3688d61379305f137397607c2ef21592172c964ebf3515c2f7dc",
        "p0150597_20050323.nc": "sha256:11dd33b36e29ebab11adf6103b9e58d047897293ee6e4bf9163346f867c1e915",
        "p0150166_20041027.nc": "sha256:7c34da34ad52e81a6c9f22897009ef792c56c9b9118b93875efec2ffd1b05900",
        "p0150037_20040929.nc": "sha256:eeab59b8c83116e84cf2e16e2db78e10911b06c27046a37e6ad7307f166eebed",
        "p0150471_20050202.nc": "sha256:6103bdc31c6f693e77a4cbdb3b9a725f77f32d5da7b65137e30346501dd86864",
        "p0150457_20050128.nc": "sha256:be45c3e837bdb032f379ba9a53dcb206580b2b0244a2e757136410b45b9d903a",
        "p0150163_20041026.nc": "sha256:883c9411461309692ce3c3d77ce2e4de03516734a76455bfbba666662cc9235c",
        "p0150032_20040928.nc": "sha256:4c6a74a63bd70fad49540efe5c9a4eedb689f989a5b00d946d41996a29e0cea8",
        "p0150004_20040924.nc": "sha256:9ef929594a3113de34c4e99391648bef1a04c07b60edb86b6c81019da16ae10a",
        "p0150568_20050311.nc": "sha256:5a2a3ffd9c7f8eed4a0d8d7c4450df0bd7431795730977e70aec3d3b9517dddc",
        "p0150474_20050203.nc": "sha256:7f94bce7e4923632242925e65c657a88e9b5b3b5624abac9efad78f542910c12",
        "p0150021_20040926.nc": "sha256:ab4cfe20dfbb6cc6f2ee999505c15ef75b10d5637699856785b0a98d684ee023",
        "p0150170_20041028.nc": "sha256:6affbd067ac1c5cf3f28f3cef27ae6d05a69f60bccf1700b8ff25bbdad4d0cb4",
        "p0150077_20041008.nc": "sha256:c8624b3e86488befa67b628b435c815b58a595bb2280f486e88ed6fe51cf4e71",
        "p0150253_20041114.nc": "sha256:a8794008a772e2a475b89080b87e2cb62a5c0078b80b0f1a1a38e10fd92a9822",
        "p0150299_20041202.nc": "sha256:59a720a795ab33a8d501f37caec5b9b0c4e68c73c359d02a8c34b08203cd6e15",
        "p0150346_20041220.nc": "sha256:b2c9d119dd9d38430e85c52c036c7fe74fd754b9757d2ba3d995ceef8cbf142e",
        "p0150338_20041217.nc": "sha256:c82bf74b5a610d081d8e6372a609d21aec5d1d40a1d5f7b0b88e4604b9846131",
        "p0150297_20041201.nc": "sha256:759cc7adc83992f3e17e9e1e14a9155f609472003d6ccb8ebc49ed3675704931",
        "p0150185_20041031.nc": "sha256:bb710e0d2fe6ef1b7d701d1824bc38248aed8356af07a80d7cebbe8139f73bc3",
        "p0150560_20050308.nc": "sha256:4e2f1d05d0379aa592379b0c9a655ca1dfdcf99a27a4af68e8c43a0cc66c0012",
        "p0150248_20041113.nc": "sha256:7af2d30466344bf2533088515248c66d9f2ac156569dfc2aaf535cbb408861c3",
        "p0150460_20050129.nc": "sha256:5d7da9e3e3dcda3839f84ae08243923e733ba2b519f6dcfc4ec5b5e27f50d71c",
        "p0150208_20041105.nc": "sha256:845439618ceb649ccd7a5fbafc92655d609af71bce6ab980b95f70b6d33cdf00",
        "p0150238_20041113.nc": "sha256:fafb728d47e71128cf6c4733d420d14def134c1e3616f666ec1f3a6ff052d689",
        "p0150189_20041101.nc": "sha256:1a79524cf0d677b36c2581a979da1ea0471c0c97585d48695ef5bc9bf0d453f5",
        "p0150342_20041218.nc": "sha256:55d6f928097878074ec517faed0aef219710d6c197bfd72ae02e2e2b653958c8",
        "p0150389_20050105.nc": "sha256:2a6e3a34132f01afbed7adc77cd3957f6469aec16f1211a244d58ccfb6b5023c",
        "p0150380_20050101.nc": "sha256:3cadc083512d299770c756c015f5ff77264526eb91e61e1e9ee4bc773e3e378f",
        "p0150564_20050310.nc": "sha256:e5ec9df44d2aaa06b284dfb5d4e289cb4affc38d57e88fd7959cd928f751247f",
        "p0150008_20040925.nc": "sha256:fa5c631f432ef1bd0ac037ff81ec1cdccf14e224387aa89d2c191e352ca7a4be",
        "p0150295_20041130.nc": "sha256:52074da3cb5ff5d54d339cca6e054f2deed7e4479640dbe9e1cce998a39db3ae",
        "p0150554_20050306.nc": "sha256:15706ab10402ad2ae2c4962bfd922bcee40696e379d748991bf203275e8afbb7",
        "p0150609_20050328.nc": "sha256:3f83a6453f511079cc073b09a9344443d0dca58df9b77e3832d4aef07bf17936",
        "p0150392_20050106.nc": "sha256:d83378dffb892355741d14ca113ed73dddd7d49c0694bc437f6cf2524c55e132",
        "p0150366_20041227.nc": "sha256:6d28fd03ebce7c18e8fa11e959b1b1bd4699d3a2222ed1cbc5123754e0d43448",
        "p0150590_20050320.nc": "sha256:c7fcacb3fac3b4a8ef57dcec1414612d6f89210a26da09cd55b6742cbcd7ef3d",
        "p0150446_20050124.nc": "sha256:8666098a72d11eaf785dfd4730c2d75ac84304ed50d34bef4449a33e5bddfeb1",
        "p0150599_20050324.nc": "sha256:219c30e8eff6a7dd4599d162b93d7fb3cc0fb063575f550a366213f2b3927371",
        "p0150192_20041102.nc": "sha256:0477b0ba843d253232675e5819eab6e3d5dbb8163ee8ee07eaafcb1359e2f6a6",
        "p0150413_20050112.nc": "sha256:e89391d15e3ba05e8847094ab6bd03ed2bf7970d1f103e26e546e8d973f0cf0d",
        "p0150308_20041205.nc": "sha256:3d04c607097ced869f19e4f468d2fdfc32b028e7c1c37d53ad4e126199cd6b2f",
        "p0150197_20041103.nc": "sha256:9de290360e49f53add24fc4a6f490b649cc7de70ec2bc84875fa2d1d843bc46d",
        "p0150148_20041023.nc": "sha256:dc93059f61ebfa9bcf4e5f24e02f3dde5a28707169cbe05587495cefc979d12d",
        "p0150416_20050113.nc": "sha256:8ff93f68da5e457ec7611c125ec1415c4eb8437cec5cff60893e9122e6c76cc9",
        "p0150063_20041005.nc": "sha256:70eb516b99a7af8abb9c0457b0d9d58639c6262b28ac7b3478859adfdc58bdf5",
        "p0150213_20041106.nc": "sha256:6daeced797ca6395c8d085dba46a5b974b85ef8f3908f406158498500c47bb35",
        "p0150492_20050210.nc": "sha256:a16999a36b5ee22e3225bab2efdb184b64d8f7484ccbaafca2af39fe5db9eea9",
        "p0150315_20041208.nc": "sha256:014103d1f3519119a1fcab2f4495702a08e278c7d1649324fd9f55fa97439e06",
        "p0150113_20041016.nc": "sha256:8ec446e94d0933c7c9d02247d07337927e42d23b29b34f88bcf58ca3bd9dceb5",
        "p0150363_20041226.nc": "sha256:3df0f12b27f9ba8733a2aaa198e28dc2c21acdd16942dc9bce5d2cc73b4b1e0b",
        "p0150271_20041121.nc": "sha256:f6e32f7735764531f14dfd04c796c1a71b1a93357c4233b9ad527b1bccaf2b2d",
        "p0150404_20050110.nc": "sha256:05844773fc14f8f781876ca8c20f1ff87d35ea2984bb462a9c2643f249b53f21",
        "p0150071_20041006.nc": "sha256:40075f91309e46a2c4efe765b50f1d1ead0f9681c89e025d7e898f54167a4351",
        "p0150451_20050126.nc": "sha256:7161b12004a344e0b3dcc94f6723eaa57cef4655c51396fc07c39a6ba8f1805d",
        "p0150534_20050226.nc": "sha256:a5b389d13b8c5c99674c16d383cd00589afaf73a2e4d069e8fa60e6bfdb84b0f",
        "p0150461_20050130.nc": "sha256:818099a04c33b94737bb4aad833747d2aefc7a060fb7124809b3195df780486c",
        "p0150153_20041024.nc": "sha256:bc1b642de677e1d602b64b7f1051697480da1fbd2937fe21001d6e704a499160",
        "p0150518_20050220.nc": "sha256:672702bd017052932dbfb0b2b10be1d70f7d09b2e9db6c61a92d7fdf1c604e05",
        "p0150241_20041113.nc": "sha256:1d6cc7256eedc658c2439747c083904a98c095b405f281d29106ebfa15e50ad7",
        "p0150582_20050317.nc": "sha256:774f00f7b62302943cc831f0c7e1764eefaf7eac52de03218c8d536eace32b96",
        "p0150104_20041014.nc": "sha256:511ecacce26c5fc9a95547a5ef2e15dbf9f278f5c2b800e34affa4701447b5ae",
        "p0150454_20050127.nc": "sha256:463b847fa09503cab86f83d08aa616d6ccbfacbdc728f910d889dac39d3dd041",
        "p0150031_20040927.nc": "sha256:13c982271af5d26164faf1aa84339e33d8a437a1e815fb787a9a1a7259c69171",
        "p0150234_20041112.nc": "sha256:3a6cfe77c75fbee2947433a190c0b6b3fd9faab3417acbfe5165250d2937dc32",
        "p0150268_20041120.nc": "sha256:3b5c73dfc22175480e6669f8f17debacce7aa48e46adb49bd985361db1212ff4",
        "p0150464_20050131.nc": "sha256:b8752f15ffe7cda42fc9dec074c00a4d3123f1b5baf2489478f406f73a07cdc8",
        "p0150156_20041025.nc": "sha256:7bf297e24fc87ee49ee6bae4d8ac0e1a8c6ca976784a02267ca2ce154bf49355",
        "p0150204_20041104.nc": "sha256:ce8ccbdb28e57a52c87992feb83f189cf6886ea5272fd236ce4a2192068f8d70",
        "p0150074_20041007.nc": "sha256:2a06a0f02492fa7a2acb3468b8c676a261d47f6f0714ebb748dc7ba8ffa1ea39",
        "p0150606_20050326.nc": "sha256:5f341bba669aa096906552dfc7d0ce6532d613ffc3ff710d2b18d65544af9760",
        "p0150014_20040925.nc": "sha256:21fd2c5f3166891288c1a3c615898916b8ca7dcf156a1dfdfa9d52729962ddd4"}
)