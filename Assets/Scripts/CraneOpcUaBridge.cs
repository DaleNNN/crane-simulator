using UnityEngine;

public class CraneOpcUaBridge : MonoBehaviour
{
    public CraneController craneController;

    private float slewAngle;
    private float boomAngle;
    private float telescopeExtension;

    // Unity automatically calls update once per frame
    void Update()
    {
        craneController.slewAngle = slewAngle;
        craneController.boomAngle = boomAngle;
        craneController.telescopeExtension = telescopeExtension;
    }

    public void SetSlewAngle(float value)
    {
        slewAngle = value;
    }

    public void SetBoomAngle(float value)
    {
        boomAngle = value;
    }

    public void SetTelescopeExtension(float value)
    {
        telescopeExtension = value;
    }
}