fetch("http://localhost:7071/api/get-app-data")
    .then((response) => response.json())
    .then((data) => renderContents(data));

function renderContents(data) {
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
        appIcon.height = 120;

        appContainer.appendChild(appIcon);
    }

    return appContainer;
}

function createAssetContainer(data) {
    let assetContainer = document.createElement("div");
    assetContainer.className = "asset";

    let osIcon = document.createElement("img");
    osIcon.src = "images/os/" + data.os + ".png";
    osIcon.height = 50;

    let downloadButton = document.createElement("a");
    downloadButton.href = data.url;
    downloadButton.className = "downloadButton";
    downloadButton.textContent = "Download";

    assetContainer.appendChild(osIcon);
    assetContainer.appendChild(downloadButton);

    return assetContainer;
}