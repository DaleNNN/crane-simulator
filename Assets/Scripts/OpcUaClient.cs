using UnityEngine;

public class OpcUaClient : MonoBehaviour
{
    public CraneController craneController;

    private float slewAngle;
    private float boomAngle;
    private float telescopeExtension;

    void Start()
    {
        // Koble til OPC UA-server
        // Subscribe på nodene
    }

    void Update()
    {
        craneController.slewAngle = slewAngle;
        craneController.boomAngle = boomAngle;
        craneController.telescopeExtension = telescopeExtension;
    }

    public void OnSlewAngleChanged(float value)
    {
        slewAngle = value;
    }

    public void OnBoomAngleChanged(float value)
    {
        boomAngle = value;
    }

    public void OnTelescopeExtensionChanged(float value)
    {
        telescopeExtension = value;
    }
}