async function refreshStatus()
{
    const response = await fetch("/status");
    const s = await response.json();

    document.getElementById("state").textContent = s.state;
    document.getElementById("program").textContent = s.program;
    document.getElementById("progress").textContent = s.progress + "%";
    document.getElementById("rpm").textContent = s.rpm + ' RPM';
    document.getElementById("feed").textContent = s.feed;
    document.getElementById("tool").textContent = s.tool;
    document.getElementById("runtime").textContent = s.runtime;
}
