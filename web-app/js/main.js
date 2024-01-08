
fetch(`https://basictranslationtooa666.blob.core.windows.net/releases/app_data.json`)
    .then((response) => response.json())
    .then((data) => renderContents(data));

function renderContents(data) {
    document.querySelector("#loader").style.display = "none";
    
    const container = document.querySelector("#tools");
    data.map((app) => {
        const appContainer = createAppContainer(app);
        const assetContainer = createAssetContainer(app);

        appContainer.appendChild(assetContainer);

        if (!container.contains(appContainer)) {
            container.appendChild(appContainer);
        }
    });
}

function createAppContainer(data) {
    let appContainer = document.querySelector("." + data.name);

    if (!appContainer) {
        appContainer = document.createElement("div")
        appContainer.classList.add(data.name);
        appContainer.classList.add("appContainer");

        const appIcon = document.createElement("img");
        appIcon.src = "images/tools/" + data.name + ".png";
        appIcon.height = 100;

        const appVersion = document.createElement("div");
        appVersion.className = "appVersion";
        appVersion.textContent = data.version;

        appContainer.appendChild(appIcon);
        appContainer.appendChild(appVersion);
    }

    return appContainer;
}

function createAssetContainer(data) {
    const assetContainer = document.createElement("div");
    assetContainer.className = "asset";

    const osIcon = document.createElement("img");
    osIcon.src = "images/os/" + data.os + ".png";
    osIcon.height = 30;

    const downloadButton = document.createElement("a");
    downloadButton.href = data.url;
    downloadButton.className = "downloadButton";
    downloadButton.textContent = "Download";

    assetContainer.appendChild(osIcon);
    assetContainer.appendChild(downloadButton);

    return assetContainer;
}